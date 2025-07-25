# models/trade_models.py

from datetime   import datetime
from decimal    import Decimal
from sqlalchemy import (
    JSON, Column, Date, Integer, DateTime, DECIMAL, Boolean, String, UniqueConstraint
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

class Symbol(Base):
    __tablename__ = "symbols"

    # Define the columns
    id                  = Column(Integer, autoincrement=True, unique=True)
    symbol              = Column(String(50), primary_key=True)
    token               = Column(String(50), nullable=True)
    name                = Column(String(50), nullable=True)
    type                = Column(String(10), nullable=False)
    price               = Column(DECIMAL(13, 2), nullable=True)
    exchange            = Column(String(20), nullable=True)
    segment             = Column(String(20), nullable=True)
    strategy            = Column(String(1000), nullable=False)
    lotsize             = Column(Integer, nullable=False, default=1)
    expiry              = Column(Date, nullable=True)
    strike_price        = Column(DECIMAL(13, 2), nullable=True)
    tick_size           = Column(DECIMAL(13, 2), nullable=True)
    equity_ref          = Column(String(50), nullable=True, index=True)
    last_time           = Column(DateTime, nullable=True)
    last_snapshot       = Column(JSON, nullable=True)
    generate_candles   = Column(Boolean, nullable=False, default=False)
    merge_candles      = Column(Boolean, nullable=False, default=False)
    update_performance = Column(Boolean, nullable=False, default=False)
    generate_signals   = Column(Boolean, nullable=False, default=False)
    processed          = Column(Boolean, nullable=False, default=False)
    active             = Column(Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<Symbol {self.symbol}>"
