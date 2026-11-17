"""Explicit photo-finish clocks and quote timing. Never substitute scheduled for actual off."""
import re
from datetime import datetime,timezone
from zoneinfo import ZoneInfo


def parse_finish_start(text,expected_date=None):
    matches=set(re.findall(r'Hora de la Salida:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)',text))
    if len(matches)!=1:raise ValueError('Require one unambiguous explicit actual-start clock')
    day,clock=matches.pop();clock=clock.replace(',','.')
    local=datetime.strptime(day+' '+clock,'%d/%m/%Y %H:%M:%S.%f' if '.' in clock else '%d/%m/%Y %H:%M:%S').replace(tzinfo=ZoneInfo('Europe/Madrid'))
    if local.replace(fold=0).utcoffset()!=local.replace(fold=1).utcoffset():raise ValueError('Ambiguous DST clock')
    if expected_date and local.date().isoformat()!=expected_date:raise ValueError('Photo-finish race date mismatch')
    return local.astimezone(timezone.utc).isoformat()


def quote_timing(quote_at,actual_start_at):
    q=datetime.fromisoformat(quote_at.replace('Z','+00:00'));a=datetime.fromisoformat(actual_start_at.replace('Z','+00:00'))
    if q.tzinfo is None or a.tzinfo is None:raise ValueError('Timezone-aware clocks required')
    seconds=(a-q).total_seconds()
    kind='last_60_seconds_before_actual_start' if 0<seconds<=60 else 'earlier_than_60_seconds_before_actual_start' if seconds>60 else 'at_or_after_actual_start'
    return seconds,kind
