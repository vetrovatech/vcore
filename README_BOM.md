# Bill of Materials (BOM) Template Guide

## Overview

The `product_bom_template.csv` file contains a Bill of Materials template for all 74 glass products in your catalog. Each product has been assigned appropriate components based on its category.

## File Structure

**Total Rows:** 383 (1 header + 382 component rows)

**Columns:**
- `product_id` - Product ID from database
- `product_name` - Product name
- `category` - Product category
- `bom_type` - BOM template type (e.g., "DGU/Insulated Glass", "Shower Enclosure")
- `component_name` - Name of the component/material
- `unit` - Unit of measurement (sqft, ft, hrs, pcs, gm, tube, etc.)
- `quantity_per_unit` - Quantity needed per unit of product (TO BE FILLED)
- `cost_per_unit` - Cost per unit of component (TO BE FILLED)
- `notes` - Additional notes about the component

## BOM Templates by Product Type

### 1. DGU/Insulated Glass
**Products:** Double Glazing Glass, Insulated Glass, Sound Proof Glass

**Components:**
- Toughened Glass (Outer) - sqft
- Toughened Glass (Inner) - sqft
- Aluminum Spacer - ft (perimeter length)
- Desiccant - gm
- Primary Sealant (Butyl) - ft
- Secondary Sealant (Silicone) - ft
- Inert Gas (Argon) - sqft
- Labor - Assembly - hrs
- Electricity - unit

### 2. Laminated Glass
**Components:**
- Toughened Glass (Top) - sqft
- Toughened Glass (Bottom) - sqft
- PVB Interlayer - sqft
- Labor - Lamination - hrs
- Electricity - Autoclave - unit

### 3. Shower Enclosure
**Components:**
- Toughened Glass - sqft
- Aluminum Profile - ft
- Hinges (SS304) - pcs
- Handle - pcs
- Rubber Gasket - ft
- Silicone Sealant - tube
- Labor - Fabrication - hrs
- Labor - Installation - hrs

### 4. Glass Partition
**Components:**
- Toughened Glass - sqft
- Aluminum U-Channel (Top) - ft
- Aluminum U-Channel (Bottom) - ft
- Rubber Gasket - ft
- Patch Fittings - set (if frameless)
- Silicone Sealant - tube
- Labor - Installation - hrs

### 5. Toughened Glass
**Components:**
- Float Glass - sqft
- Labor - Cutting - hrs
- Labor - Edging - hrs
- Electricity - Tempering - unit

### 6. Etched/Frosted Glass
**Components:**
- Float Glass - sqft
- Acid/Sandblasting Material - sqft
- Labor - Etching - hrs
- Electricity - Tempering - unit (if toughened)

### 7. Mirror Glass
**Components:**
- Float Glass - sqft
- Silver Coating - sqft
- Protective Paint - sqft
- Labor - Processing - hrs

## How to Use

### Step 1: Fill in Quantities
Open the CSV and fill in the `quantity_per_unit` column for each component:

**Example for DGU Glass (per sqft of finished product):**
```
Toughened Glass (Outer): 1.0 sqft
Toughened Glass (Inner): 1.0 sqft
Aluminum Spacer: 4.0 ft (for 1 sqft = ~12" x 12" = 48" perimeter)
Desiccant: 10 gm
Primary Sealant: 4.0 ft
Secondary Sealant: 4.0 ft
Inert Gas (Argon): 1.0 sqft
Labor - Assembly: 0.25 hrs
Electricity: 1.0 unit
```

### Step 2: Fill in Costs
Add the `cost_per_unit` for each component based on your supplier rates.

### Step 3: Calculate Total Cost
You can then calculate:
- **Material Cost** = Σ(quantity × cost) for all materials
- **Labor Cost** = Σ(hours × hourly_rate) for all labor
- **Total BOM Cost** = Material Cost + Labor Cost + Electricity Cost

### Step 4: Add Markup
Add your markup percentage to get the selling price:
```
Selling Price = Total BOM Cost × (1 + Markup %)
```

## Example: DGU Glass Calculation

**Product:** Double Glazing Glass (1 sqft)

| Component | Qty | Unit | Cost/Unit | Total |
|-----------|-----|------|-----------|-------|
| Toughened Glass (Outer) | 1.0 | sqft | ₹150 | ₹150 |
| Toughened Glass (Inner) | 1.0 | sqft | ₹150 | ₹150 |
| Aluminum Spacer | 4.0 | ft | ₹20 | ₹80 |
| Desiccant | 10 | gm | ₹2 | ₹20 |
| Primary Sealant | 4.0 | ft | ₹5 | ₹20 |
| Secondary Sealant | 4.0 | ft | ₹8 | ₹32 |
| Argon Gas | 1.0 | sqft | ₹30 | ₹30 |
| Labor - Assembly | 0.25 | hrs | ₹200 | ₹50 |
| Electricity | 1.0 | unit | ₹20 | ₹20 |
| **Total BOM Cost** | | | | **₹552** |
| Markup (30%) | | | | ₹166 |
| **Selling Price** | | | | **₹718/sqft** |

## Next Steps

1. ✅ Review the BOM template
2. ⏳ Fill in accurate quantities based on your production process
3. ⏳ Add current supplier costs
4. ⏳ Calculate total costs for each product
5. ⏳ Use for quotations and pricing strategy

## Customization

You can modify the template:
- Add/remove components for specific products
- Adjust quantities based on actual usage
- Add overhead costs (rent, utilities, admin)
- Include wastage factors

## Import to Database (Future)

Once finalized, this BOM data can be imported into a database table for:
- Automated cost calculations
- Quotation generation
- Inventory management
- Production planning
