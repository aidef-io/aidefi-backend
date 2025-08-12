from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal

class SwapDto(BaseModel):
    chainID: str = Field(default="ethereum")
    inputToken: str
    outputToken: str
    inputAmount: str
    userAddress: str
    slippage: float
