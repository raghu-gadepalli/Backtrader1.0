from enum import Enum

class BaseEnum(Enum):
    @classmethod
    def from_string(cls, value):
        # if they already passed in an enum, return it directly
        if isinstance(value, cls):
            return value

        norm = value.strip().upper().replace(" ", "_")
        for member in cls:
            if member.name == norm or member.value.upper() == norm:
                return member
        raise ValueError(f"Unknown value for {cls.__name__}: {value!r}")


    def to_string(self) -> str:
        """
        Returns a standardized string representation of the enum member.
        """
        return self.name.upper()


# -----------------------------
# Enums from order.py
# -----------------------------
class OrderVariety(BaseEnum):
    REGULAR = "regular"
    AMO = "amo"
    ICEBERG = "iceberg"


class OrderType(BaseEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SL-M"


class ProductType(BaseEnum):
    CNC = "CNC"
    MIS = "MIS"
    NRML = "NRML"


class OrderStatus(BaseEnum):
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"  
    REJECTED = "REJECTED"
    PENDING = "PENDING"
    OPEN = "OPEN"
    INVALID = "INVALID"
    TRIGGER_PENDING = "TRIGGER PENDING"


    @classmethod
    def from_string(cls, value: str) -> "OrderStatus":
        # Using the base class behavior.
        return super().from_string(value)


# -----------------------------
# Enums from symbol_type.py
# -----------------------------
class SymbolType(BaseEnum):
    EQ = "EQ"  # Equity
    CE = "CE"  # Call Option
    PE = "PE"  # Put Option
    FUT = "FUT"  # Future


# -----------------------------
# Enums from trade_status.py
# -----------------------------
class TradeStatus(BaseEnum):
    OPEN                   = "OPEN"                    # nothing sent yet
    ENTRY_PLACED           = "ENTRY_PLACED"            # entry order accepted by broker
    ENTRY_FILLED           = "ENTRY_FILLED"            # entry actually filled (no SL yet)
    SL_INITIATED           = "SL_INITIATED"            # new: weve kicked off the SL placement
    SL_PLACED              = "SL_PLACED"               # hard SL order confirmed by broker
    SL_FILLED              = "SL_FILLED"               # hard SL order filled 
    SL_EXECUTED            = "SL_EXECUTED"             # SL order filled  trade is over
    COMPLETE               = "COMPLETE"                # final, userconfirmed completion
    CANCELLED_RETRY_LIMIT  = "CANCELLED_RETRY_LIMIT"   # retries exhausted, cancelled
    CANCELLED              = "CANCELLED"               # explicit cancel
    INVALID                = "INVALID"                 # error/unexpected
    REJECTED               = "REJECTED"                # hard rejection by broker

# -----------------------------
# Enums from trade_type.py
# -----------------------------
class TradeType(BaseEnum):
    BUY = "BUY"
    SELL = "SELL"

# -----------------------------
# Enums from stoploss_type.py
# -----------------------------

class StopLossType(BaseEnum):
    PERCENT = "PERCENT"
    HMA     = "HMA"
    ATR     = "ATR"

# -----------------------------
# Enums from trailing_stoploss_type.py
# -----------------------------
class TrailingStoplossType(BaseEnum):
    STEP  = "step"
    COST  = "cost"
    HMA   = "hma"
    ATR   = "atr"


# -----------------------------
# Enums from trend_type.py
# -----------------------------
class TrendType(BaseEnum):
    BUY = "BUY"
    SELL = "SELL"
    NO_TREND = "NO_TREND"


# -----------------------------
# Enums from exchange_type.py
# -----------------------------
class ExchangeType(BaseEnum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    DEFAULT = "DEFAULT"


# -----------------------------
# Enums from indicator_type.py
# -----------------------------
class IndicatorType(BaseEnum):
    HMA = "HMA"
