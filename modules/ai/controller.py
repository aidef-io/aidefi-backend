import json
import os
from fastapi import APIRouter
import google.generativeai as genai
from dotenv import load_dotenv

from modules.classes.service import ChatResponse, ChatRequest, TransactionData, MultiSendWallet, UnifiedAIAgent, WalletData

# Çevre değişkenlerini yükle
load_dotenv()

# API anahtarını çevre değişkenlerinden al
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")

genai.configure(api_key=GEMINI_API_KEY)

router = APIRouter()

# Tek unified agent'ı başlat
unified_agent = UnifiedAIAgent()

import re

def clean_value(val: str) -> str:
    """
    Frontend ile uyumlu olacak şekilde değerleri temizler
    """
    if not isinstance(val, str):
        return ""
    
    # Frontend'deki temizleme işlemleriyle uyumlu hale getir
    cleaned = val.strip()
    cleaned = re.sub(r"```(?:json)?|```|\n", "", cleaned)
    cleaned = cleaned.replace('"', '').replace("'", '')
    cleaned = cleaned.strip()
    
    return cleaned

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Optimize edilmiş chat endpoint'i - tek API çağrısı ile tüm işlemler
    """
    try:
        # Mevcut transaction_data'yı al veya yeni bir tane oluştur
        current_transaction_data = request.transaction_data or TransactionData()
        # print(f"Current Transaction Data: {current_transaction_data}")
        wallet_data = request.wallet_data or WalletData()
        # print(f"Current Wallet Data: {wallet_data}")
        
        # TEK API ÇAĞRISI ile tüm işlemleri gerçekleştir
        final_response, updated_transaction_data = await unified_agent.process_message(
            request.message, 
            wallet_data,
            current_transaction_data
        )
        # print(f"Final Response: {final_response}")
        
        # Değerleri frontend formatına uygun şekilde temizle
        updated_transaction_data.transaction_type = clean_value(updated_transaction_data.transaction_type or "")
        updated_transaction_data.token_type = clean_value(updated_transaction_data.token_type or "")
        updated_transaction_data.amount = clean_value(updated_transaction_data.amount or "")
        updated_transaction_data.chain = clean_value(updated_transaction_data.chain or "")
        updated_transaction_data.destination_wallet_address = clean_value(updated_transaction_data.destination_wallet_address or "")
        
        print(f"Transaction Data: {updated_transaction_data}")
        print(f"Final Response: {final_response}")
        
        return ChatResponse(
            response=final_response,
            transaction_data=updated_transaction_data,
            status="success"
        )
        
    except Exception as e:
        # Frontend'in beklediği hata formatında yanıt ver
        return ChatResponse(
            response=f"Sorry, there was an error processing your message: {str(e)}",
            transaction_data=TransactionData(),
            status="error"
        )
