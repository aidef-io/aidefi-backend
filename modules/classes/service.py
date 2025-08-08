import google.generativeai as genai
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WalletData(BaseModel):
    address: Optional[List[str]] = None

class MultiSendWallet(BaseModel):
    destination_wallet_address: str
    destination_wallet_amount: str

class TransactionData(BaseModel):
    transaction_type: Optional[str] = None
    chain: Optional[str] = None
    token_type: Optional[str] = None
    amount: Optional[str] = None
    destination_wallet_address: Optional[str] = None
    multi_send_wallets: Optional[List[MultiSendWallet]] = None
    source_wallet_address: Optional[str] = None
    source_token: Optional[str] = None
    receive_token: Optional[str] = None
    slippage_tolerance: Optional[str] = None

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=2048)
    transaction_data: Optional[TransactionData] = None
    wallet_data: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None
    context: Optional[List[Dict[str, str]]] = Field(default_factory=list)

class ChatResponse(BaseModel):
    response: str
    transaction_data: TransactionData
    status: str

# Tek AI Agent sınıfı - tüm işlemleri tek seferde yapar
class UnifiedAIAgent:
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model = genai.GenerativeModel(model_name)

    async def process_message(self, message: str, current_wallet_data: WalletData , current_transaction_data: TransactionData = None) -> tuple[str, TransactionData]:
        current_data = current_transaction_data or TransactionData()
        wallet_data = current_wallet_data or WalletData()
        
        system_message = f"""
        You are a comprehensive DeFi assistant that analyzes user messages and extracts transaction information in a single response.

        CURRENT TRANSACTION DATA:

        !!!!!!!! IF THE USER MAKES A MISTAKE ABOUT ALREADY EXISTING DATA AND IF THE USER TELLS YOU "I MADE A MISTAKE" OR "I WANT TO CHANGE" OR "I WANT TO UPDATE" OR "I WANT TO CORRECT" OR "I WANT TO EDIT" OR "I WANT TO MODIFY" OR "I WANT TO REPLACE" OR "I WANT TO RESET" OR "I WANT TO CLEAR" OR "I WANT TO DELETE", THEN YOU MUST UPDATE THE CURRENT DATA WITH THE NEW DATA. !!!!!!!!
            Transaction Type: {current_data.transaction_type or ""}
            Chain: {current_data.chain or ""}
            Token Type: {current_data.token_type or ""}
            Amount: {current_data.amount or ""}
            Destination Address: {current_data.destination_wallet_address or ""}
            Multi Send Wallets: {json.dumps([wallet.dict() for wallet in current_data.multi_send_wallets]) if current_data.multi_send_wallets else "[]"}
            Source Wallet Address: {current_data.source_wallet_address or ""}
            Source Token: {current_data.source_token or ""}
            Receive Token: {current_data.receive_token or ""}
            Slippage Tolerance: {current_data.slippage_tolerance or ""}
            wallet_data: {wallet_data} (all the wallet_data usage refer to this equality where the use in analysis tasks part explains below)
            ANALYSIS TASKS:
            Transaction Type Detection: Determine if this is 'multisend', 'merge', or 'swap'
            Multisend: ONE wallet to MULTIPLE wallets
            Merge: MULTIPLE wallets to ONE wallet
            Swap: Converting tokens within ONE wallet (requires source_wallet_address, source_token, amount, receive_token, slippage_tolerance)
            Chain Detection: Extract blockchain from: "ethereum", "Sepolia", "polygon", "optimism", "arbitrum", "base", "bsc", "bscTestnet"
            Token Type: Extract token symbol (USDT, BNB, ETH, etc.)
            User could make a mistake about ticker symbol, like "USDT" instead of "usdt", so you must handle this case.
            Amount: Extract total transaction amount (numbers only)
            Address Detection:
            For Merge: Extract destination wallet address
            For Multisend: Extract all destination addresses with amounts
            If the user wants to send tokens to one of their own wallets (e.g., "send to my first wallet", "merge to my second wallet", or "send to my fourth wallet"), you must use the corresponding address from wallet_data, based on the specified index, as the destination_wallet_address.
            For Swap: Extract source_wallet_address from wallet_data if user refers to their own wallet for example, "swap from my first wallet" or "swap from my second wallet" or "swap from my third wallet", etc.
            Swap Specific Fields:
            source_wallet_address: The wallet that will perform the swap
            source_token: The token being sold/swapped
            receive_token: The token to receive in the swap
            slippage_tolerance: Acceptable slippage for the swap (e.g., 0.5%, 1%, %2 or user could just say "slippage tolerance is 1" or "slippage is 0.5" or "slippage tolerance is 2%")
            Final Response: Generate appropriate user response based on:
            Social greetings: Respond friendly and briefly
            Non-DeFi questions: "I'm a DeFi assistant. How may I help you with DeFi?"
            Transaction processing: Validate required fields and provide guidance
            RESPONSE FORMAT (JSON): {{ "transaction_type": "extracted_type_or_current", "chain": "extracted_chain_or_current", "token_type": "extracted_token_or_current", "amount": "extracted_amount_or_current", "destination_wallet_address": "extracted_address_or_current", "multi_send_wallets": [ {{"destination_wallet_address": "address", "destination_wallet_amount": "amount"}} ], "source_wallet_address": "extracted_source_wallet_or_current", "source_token": "extracted_source_token_or_current", "receive_token": "extracted_receive_token_or_current", "slippage_tolerance": "extracted_slippage_or_current", "user_response": "Generated response for user" }}
            VALIDATION RULES:
            Merge requires: chain, token_type, amount, destination_wallet_address
            Multisend requires: chain, token_type, amount, multi_send_wallets
            Swap requires: chain, source_wallet_address, source_token, receive_token, amount, slippage_tolerance
            Only update fields if new information is found
            Keep existing values if no new data is detected
            Return empty string for missing fields, not null
            USER MESSAGE: {message}
            """

        try:
            response = self.model.generate_content(system_message)
            result = response.text.strip()
            
            # JSON response'u parse et
            # Markdown kod bloklarını temizle
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                result = result.split("```")[1].split("```")[0].strip()
            
            try:
                parsed_response = json.loads(result)
                
                # TransactionData'yı güncelle
                # Check if transaction type is multisend or swap
                is_multisend = parsed_response.get("transaction_type") == "multisend"
                is_swap = parsed_response.get("transaction_type") == "swap"

                updated_transaction_data = TransactionData(
                    transaction_type=parsed_response.get("transaction_type") or current_data.transaction_type,
                    chain=parsed_response.get("chain") or current_data.chain,
                    token_type=parsed_response.get("token_type") or current_data.token_type,
                    amount=parsed_response.get("amount") or current_data.amount,
                    # Set destination_wallet_address to None for multisend and swap
                    destination_wallet_address=None if (is_multisend or is_swap) else (parsed_response.get("destination_wallet_address") or current_data.destination_wallet_address),
                    multi_send_wallets=[
                        MultiSendWallet(**wallet) for wallet in parsed_response.get("multi_send_wallets", [])
                    ] if parsed_response.get("multi_send_wallets") else current_data.multi_send_wallets,
                    # Swap specific fields
                    source_wallet_address=parsed_response.get("source_wallet_address") or current_data.source_wallet_address,
                    source_token=parsed_response.get("source_token") or current_data.source_token,
                    receive_token=parsed_response.get("receive_token") or current_data.receive_token,
                    slippage_tolerance=parsed_response.get("slippage_tolerance") or current_data.slippage_tolerance
                )
                
                user_response = parsed_response.get("user_response", "I'm here to help with your DeFi transactions!")
                
                return user_response, updated_transaction_data
                
            except json.JSONDecodeError:
                # JSON parse edilemezse fallback response
                return "I'm processing your request. Could you please provide more details about your transaction?", current_data
                
        except Exception as e:
            print(f"Error in unified processing: {e}")
            return "Sorry, I encountered an error. Please try again.", current_data