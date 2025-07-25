# data/get_symbols.py

from typing    import List, Optional, Tuple
from config.db import get_session
from models.trade_models import Symbol

def fetch_symbols(
    active: Optional[bool] = None,
    type_filter: Optional[str] = None
) -> List[Tuple[str, int]]:
    """
    Return a list of (symbol, token) tuples from the Symbol table, filtered by:
       active flag (if not None)
       generate_signals flag (if not None)
       type (if not None, e.g. 'EQ')
    By default (all args None), returns every symbol/token.
    """
    with get_session() as session:
        q = session.query(Symbol.symbol, Symbol.token)
        if active is not None:
            q = q.filter(Symbol.active == active)
        if type_filter is not None:
            q = q.filter(Symbol.type == type_filter)
        return [(row.symbol, row.token) for row in q.all()]
