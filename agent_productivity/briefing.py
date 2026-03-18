"""
Morning briefing aggregation logic.
"""
from datetime import datetime
from typing import Optional
from productivity.models import Briefing, TodoItem


def generate_briefing(date: datetime, todos_due: list[TodoItem], calendar_events: list[dict]) -> Briefing:
    """
    Aggregation for a morning briefing.
    In a real system, this would poll weather APIs and news as well.
    """
    briefing = Briefing(
        date=date,
        weather_summary="Sunny with a chance of productive turns.",
        todos_due=todos_due,
        calendar_events=calendar_events,
        news_summary="Agent OS continues to evolve with new modules."
    )
    return briefing


def format_briefing(briefing: Briefing) -> str:
    """Format briefing as markdown for the LLM or user."""
    lines = [f"# Morning Briefing - {briefing.date.strftime('%Y-%m-%d')}"]
    lines.append(f"🌤 Weather: {briefing.weather_summary}")
    
    lines.append("\n## ✅ To-dos Due Today")
    if not briefing.todos_due:
        lines.append("- No pressing tasks.")
    for todo in briefing.todos_due:
        lines.append(f"- [{todo.priority}] {todo.title} ({todo.status})")
        
    lines.append("\n## 📅 Calendar")
    if not briefing.calendar_events:
        lines.append("- Open day.")
    for event in briefing.calendar_events:
        lines.append(f"- {event.get('title')} at {event.get('time')}")
        
    lines.append(f"\n## 📰 Highlights\n{briefing.news_summary}")
    
    return "\n".join(lines)
