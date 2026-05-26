"""One-off cleanup for bathqube quotes that got double-counted by the
delete()+flush() bug in bathqube_quote_revise (fixed by switching to
quote.items.clear()).

Symptom: quote.subtotal stored as sum(OLD + NEW items), while the DB only
contains the NEW items. The revision snapshot is also contaminated.

Strategy:
  1. For every bathqube_quote with revision_count > 0, recompute subtotal
     from the actual rows in bathqube_quote_items.
  2. If stored subtotal != recomputed, fix subtotal/cgst/sgst/total/
     revised_total/balance_payable consistent with the discount-before-GST
     rule. Discount % is preserved from the quote.
  3. Print before/after so we have an audit trail.

Snapshots in bathqube_quote_revisions are LEFT ALONE — they are historic
records and rewriting them would defeat the purpose of an audit log. The
view page already shows them collapsed; ops can read them knowing the bug
existed.

Run inside the container:
    docker exec -it vcore-vcore-1 python cleanup_bathqube_double_counted.py
"""

import os
from decimal import Decimal

os.environ.setdefault('FLASK_APP', 'app.py')

from app import app, db
from models import BathqubeQuote


def q2(v):
    return Decimal(v or 0).quantize(Decimal('0.01'))


def fix_quote(quote):
    actual_subtotal = sum((Decimal(it.amount or 0) for it in quote.items), Decimal('0'))
    stored_subtotal = Decimal(quote.subtotal or 0)

    if q2(actual_subtotal) == q2(stored_subtotal):
        return False

    discount_pct = Decimal(quote.discount_percent or 0)
    discount_amt = (actual_subtotal * discount_pct / Decimal('100')) if discount_pct else Decimal('0')
    taxable = max(Decimal('0'), actual_subtotal - discount_amt)
    gst_pct = Decimal(quote.gst_percentage or 18)
    half = gst_pct / Decimal('2')
    cgst = taxable * half / Decimal('100')
    sgst = taxable * half / Decimal('100')
    total = taxable + cgst + sgst

    print(f"  Quote {quote.id} ({quote.estimate_number or '-'}) rev={quote.revision_count}")
    print(f"    items in DB: {len(quote.items)}  recomputed subtotal: {q2(actual_subtotal)}")
    print(f"    stored subtotal: {q2(stored_subtotal)}  stored total: {q2(quote.total)}")
    print(f"    -> new subtotal {q2(actual_subtotal)}  discount {q2(discount_amt)}  total {q2(total)}")

    quote.subtotal = q2(actual_subtotal)
    quote.discount_amount = q2(discount_amt)
    quote.cgst = q2(cgst)
    quote.sgst = q2(sgst)
    quote.total = q2(total)
    if quote.has_revision:
        quote.revised_total = q2(total)
    # balance_payable is a derived property — no setter, recomputed on read.
    return True


def main():
    with app.app_context():
        candidates = (BathqubeQuote.query
                      .filter(BathqubeQuote.revision_count > 0)
                      .order_by(BathqubeQuote.id).all())
        print(f"Scanning {len(candidates)} revised quotes...\n")
        fixed = 0
        for q in candidates:
            if fix_quote(q):
                fixed += 1
        if fixed:
            db.session.commit()
            print(f"\nCommitted fixes for {fixed} quote(s).")
        else:
            print("\nNothing to fix — all revised quotes already consistent.")


if __name__ == '__main__':
    main()
