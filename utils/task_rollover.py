from datetime import datetime, timedelta
from models import db, PromotorTask


def rollover_incomplete_tasks():
    """
    Rollover incomplete tasks from previous weeks to current week.
    Returns a summary of rolled-over tasks.
    """
    current_date = datetime.now()
    current_week = current_date.isocalendar()[1]
    current_year = current_date.isocalendar()[0]
    
    # Get all incomplete tasks from previous weeks
    incomplete_tasks = PromotorTask.query.filter(
        PromotorTask.status.in_(['Pending', 'In Progress', 'Overdue']),
        db.or_(
            PromotorTask.assigned_year < current_year,
            db.and_(
                PromotorTask.assigned_year == current_year,
                PromotorTask.assigned_week < current_week
            )
        )
    ).all()
    
    rollover_count = 0
    rollover_summary = []
    
    for task in incomplete_tasks:
        # Update task to current week
        task.assigned_week = current_week
        task.assigned_year = current_year
        
        # Calculate and update lag
        task.update_lag()
        
        # Update status to Overdue if it has lag
        if task.lag_weeks > 0:
            task.status = 'Overdue'
        
        # Update due date to end of current week
        days_until_sunday = 6 - current_date.weekday()  # Sunday is end of week
        task.due_date = (current_date + timedelta(days=days_until_sunday)).date()
        
        task.updated_at = datetime.utcnow()
        
        rollover_count += 1
        rollover_summary.append({
            'task_id': task.id,
            'template_name': task.template.name if task.template else 'N/A',
            'promotor': task.promotor.username if task.promotor else 'N/A',
            'lag_weeks': task.lag_weeks,
            'original_week': f"{task.original_week}/{task.original_year}"
        })
    
    # Commit all changes
    db.session.commit()
    
    return {
        'count': rollover_count,
        'tasks': rollover_summary,
        'current_week': current_week,
        'current_year': current_year
    }


def get_current_week_info():
    """Get current week number and year"""
    current_date = datetime.now()
    return {
        'week': current_date.isocalendar()[1],
        'year': current_date.isocalendar()[0],
        'date': current_date.date()
    }


def get_week_date_range(week, year):
    """Get start and end dates for a given week"""
    # Get first day of the year
    jan_1 = datetime(year, 1, 1)
    
    # Calculate the start of the week
    days_to_week = (week - 1) * 7
    week_start = jan_1 + timedelta(days=days_to_week - jan_1.weekday())
    week_end = week_start + timedelta(days=6)
    
    return {
        'start': week_start.date(),
        'end': week_end.date()
    }
