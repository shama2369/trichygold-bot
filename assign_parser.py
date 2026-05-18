"""Parse /assign command arguments (shared by production bot)."""
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

_TIME_RE = re.compile(r'^(\d+)([mhd])$', re.IGNORECASE)
_PRIORITIES = frozenset({'low', 'normal', 'medium', 'high'})
_DUE_KEYWORDS = {
    'today': 0,
    'tomorrow': 1,
    'nextweek': 7,
}


def parse_assign_args(args: List[str]) -> Tuple[List[str], str, int, Optional[str], Optional[str]]:
    """
    Parse Telegram /assign args (already split on whitespace).

    Format: employee[,employee2...] <task words...> [30m] [p:high|low|...] [due:tomorrow|...]
    Also accepts bare priority (low/high/medium) and due keywords (tomorrow/today).

    Returns:
        employee_names, task_description, reminder_minutes, priority, due_date (YYYY-MM-DD or str)
    """
    if len(args) < 2:
        raise ValueError("Need at least employee name and task description")

    employee_names = [n.strip() for n in args[0].split(',') if n.strip()]
    task_parts = args[1:]

    minutes = 60
    priority: Optional[str] = 'normal'
    due_date: Optional[str] = None
    description_parts: List[str] = []

    for part in task_parts:
        lower = part.lower()

        time_match = _TIME_RE.match(lower)
        if time_match:
            value, unit = time_match.groups()
            value = int(value)
            if unit == 'm':
                minutes = value
            elif unit == 'h':
                minutes = value * 60
            else:
                minutes = value * 60 * 24
            continue

        if lower.startswith('p:'):
            pval = lower[2:]
            if pval in _PRIORITIES:
                priority = pval
            continue

        if lower.startswith('due:'):
            due_date = _resolve_due(lower[4:])
            continue

        if lower in _PRIORITIES:
            priority = lower
            continue

        if lower in _DUE_KEYWORDS:
            due_date = _resolve_due(lower)
            continue

        if lower.isdigit():
            minutes = int(lower)
            continue

        description_parts.append(part)

    task_description = ' '.join(description_parts).strip()
    if not task_description:
        raise ValueError("Task description is required")

    return employee_names, task_description, minutes, priority, due_date


def _resolve_due(value: str) -> str:
    """Turn due: value or keyword into a display/storage date string."""
    value = value.lower().strip()
    if value in _DUE_KEYWORDS:
        days = _DUE_KEYWORDS[value]
        return (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
    return value


ASSIGN_USAGE = (
    "📝 *Task Assignment*\n\n"
    "`/assign employee1,employee2 <task description> [time] [priority] [due]`\n\n"
    "*Required:* employee name(s), task description (can be multiple words)\n\n"
    "*Optional:*\n"
    "• Time: `36m`, `2h`, `1d`\n"
    "• Priority: `p:low` / `p:high` or bare `low` / `high`\n"
    "• Due: `due:tomorrow` or bare `tomorrow` / `today`\n\n"
    "*Example:*\n"
    "`/assign swathy chk punch 36m p:low due:tomorrow`"
)
