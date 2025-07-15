# models/trade_models.py

from datetime   import datetime
from decimal    import Decimal
from sqlalchemy import (
    Column, Integer, DateTime, DECIMAL, Boolean, String, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "frequency", "candle_time", name="symbol_frequency_ctime"),
    )

    id          = Column(Integer, primary_key=True, autoincrement=True)
    symbol      = Column(String(50), nullable=False)
    frequency   = Column(Integer, nullable=False)       # minutes (1, 3, 5, )
    candle_time = Column(DateTime, nullable=False)
    open        = Column(DECIMAL(13, 2), nullable=False, default=Decimal("0.00"))
    high        = Column(DECIMAL(13, 2), nullable=False, default=Decimal("0.00"))
    low         = Column(DECIMAL(13, 2), nullable=False, default=Decimal("0.00"))
    close       = Column(DECIMAL(13, 2), nullable=False, default=Decimal("0.00"))
    volume      = Column(DECIMAL(13, 2), nullable=False, default=Decimal("0.00"))
    oi          = Column(DECIMAL(13, 2), nullable=False, default=Decimal("0.00"))
    active      = Column(Boolean, nullable=False, default=True)

    def __repr__(self):
        ts = self.candle_time.isoformat()
        return f"<Candle {self.symbol} {self.frequency}m @ {ts}>"
