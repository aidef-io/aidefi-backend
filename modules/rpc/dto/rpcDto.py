from pydantic import BaseModel
from typing import List

class rpcDTO(BaseModel):
    addresses: List[str]
    chain: int  # Default to Ethereum mainnet