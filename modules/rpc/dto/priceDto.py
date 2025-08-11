from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PriceDto:
    inputToken: str
    outputToken: str
    inputAmount: str
    userAddress: str
    chainID: str
    slippage: Optional[float] = None

