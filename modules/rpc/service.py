
from datetime import datetime
from dotenv import load_dotenv
import requests
import time
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.rpc.dto.priceDto import PriceDto
from modules.rpc.dto.rpcDto import rpcDTO

load_dotenv()
# RPC ve CMC API anahtarlarını .env dosyasından al
RPC_KEY = os.getenv("RPC_KEY")
if not RPC_KEY:
    raise ValueError("RPC_KEY environment variable is not set. Please set it in the .env file.")
CMC_API_KEY = os.getenv("CMC_API_KEY")
if not CMC_API_KEY:
    raise ValueError("CMC_API_KEY environment variable is not set. Please set it in the .env file.")

SWAP_API_KEY = os.getenv("SWAP_API_KEY")
if not SWAP_API_KEY:
    raise ValueError("SWAP_API_KEY environment variable is not set. Please set it in the .env file.")

NATIVE_TOKEN_MAPPING = {
    "ethereum": "ETH",
    "bsc": "BNB", 
    "polygon": "MATIC",
    "avalanche": "AVAX",
    "arbitrum": "ETH",
    "optimism": "ETH"
}

class SimpleTokenCache:
    def __init__(self):
        self.cache_file = "token_cache.json"
        self.cache = self.load_cache()
        self.cache_loaded = False
    
    def load_cache(self):
        """Cache dosyasını yükle"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                
                # Bugünün tarihi
                today = datetime.now().strftime('%Y-%m-%d')
                
                # Cache bugünden değilse temizle
                if data.get('date') != today:
                    print(f"Eski cache temizlendi. Yeni tarih: {today}")
                    return {'date': today, 'tokens': {}}
                
                print(f"Cache yüklendi. Tarih: {today}, Token sayısı: {len(data.get('tokens', {}))}")
                return data
            except Exception as e:
                print(f"Cache yükleme hatası: {e}")
        
        # Yeni cache oluştur
        today = datetime.now().strftime('%Y-%m-%d')
        print(f"Yeni cache oluşturuldu. Tarih: {today}")
        return {'date': today, 'tokens': {}}
    
    def save_cache(self):
        """Cache'i kaydet"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
            print(f"Cache kaydedildi. Token sayısı: {len(self.cache.get('tokens', {}))}")
        except Exception as e:
            print(f"Cache kaydetme hatası: {e}")
    
    def get_cached_price_by_symbol(self, symbol):
        """Token fiyatını cache'den al"""
        cached_data = self.cache['tokens'].get(symbol.lower())
        # if cached_data:
        #     print(f"Cache'den alindi: {symbol} - {cached_data}")
        return cached_data
    
    def set_cached_price_by_symbol(self, symbol, price_info):
        """Token fiyatını cache'e kaydet"""
        self.cache['tokens'][symbol.lower()] = price_info
        print(f"Cache'e eklendi: {symbol} - {price_info}")
        self.save_cache()
    
    def cleanup_old_cache(self):
        """Eski cache'i temizle (sadece tarih farklıysa)"""
        today = datetime.now().strftime('%Y-%m-%d')
        if self.cache.get('date') != today:
            print(f"Cache tarihi eski, temizleniyor: {self.cache.get('date')} -> {today}")
            self.cache = {'date': today, 'tokens': {}}
            self.save_cache()

# Cache instance'ı oluştur
price_cache = SimpleTokenCache()

class RPCService:
    def info(rpc_request: rpcDTO):
        wallet_results = []
        unique_tokens_by_contract = {}
        all_token_symbols = set()
        
        # 1. ADIM: Paralel olarak cüzdan token bilgilerini getir
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Her cüzdan adresi için token getirme işlemini başlat
            address_to_future = {
                executor.submit(RPCService.fetch_address_tokens, rpc_request.chain, wallet_address): wallet_address 
                for wallet_address in rpc_request.addresses
            }
            
            # Tamamlanan işlemleri kontrol et
            for completed_future in as_completed(address_to_future):
                current_address = address_to_future[completed_future]
                
                try:
                    # Token verilerini al
                    token_list = completed_future.result()
                    
                    # Sonuçlara ekle
                    wallet_results.append({
                        "address": current_address, 
                        "tokens": token_list
                    })
                    
                    # Benzersiz token'ları topla (fiyat bilgisi için)
                    for token_info in token_list:
                        token_symbol = token_info.get("symbol")
                        if token_symbol:
                            all_token_symbols.add(token_symbol)
                        contract_address = token_info.get("contractAddress")
                        if contract_address is not None:
                            normalized_address = contract_address.lower()
                            unique_tokens_by_contract[normalized_address] = token_info
                            
                except Exception as error:
                    print(f"❌ Hata - Cüzdan adresi {current_address} için token bilgileri alınamadı:")
                    print(f"   Hata detayı: {error}")

            if unique_tokens_by_contract or all_token_symbols:
                # Benzersiz token sembollerini topla (native token'lar dahil)
                unique_symbols = list(set([
                    token_info["symbol"] 
                    for token_info in unique_tokens_by_contract.values()
                    if token_info.get("symbol")
                ]))
                
                # Native token'ları da ekle
                unique_symbols.extend(list(all_token_symbols))
                unique_symbols = list(set(unique_symbols))  # Duplicate'ları kaldır
                
                # print(f"📊 Fiyat bilgisi alınacak token sembolleri: {unique_symbols}")
                
                # CoinMarketCap'ten fiyat bilgilerini al (filtreleme ile)
                token_prices = RPCService.get_token_prices_from_cmc(unique_symbols)
                
                # Her cüzdan sonucuna fiyat bilgilerini ekle ve geçersiz tokenları filtrele
                for wallet_result in wallet_results:
                    filtered_tokens = []
                    for token in wallet_result["tokens"]:
                        token_symbol = token.get("symbol", "").lower()
                        
                        # Native token'lar her zaman geçerli kabul edilir
                        if token.get("isNative", False):
                            price_data = token_prices.get(token_symbol, {})
                            token["price_usd"] = price_data.get("usd", 0)
                            token["price_change_24h"] = price_data.get("percent_change_24h", 0)
                            token["market_cap"] = price_data.get("market_cap", 0)
                            
                            # Toplam değeri hesapla
                            token_balance = token.get("balance", 0)
                            token_price = token.get("price_usd", 0)
                            if token_price is None:
                                token["total_value_usd"] = 0 
                            else:
                                token["total_value_usd"] = token_balance * token_price
                            
                            filtered_tokens.append(token)
                        else:
                            # ERC-20 tokenlar için geçerlilik kontrolü
                            # if token_symbol in valid_tokens:
                                price_data = token_prices.get(token_symbol, {})
                                token["price_usd"] = price_data.get("usd", 0)
                                token["price_change_24h"] = price_data.get("percent_change_24h", 0)
                                token["market_cap"] = price_data.get("market_cap", 0)
                                
                                # Toplam değeri hesapla
                                token_balance = token.get("balance", 0)
                                token_price = token.get("price_usd", 0)
                                if token_price is None:
                                    token["total_value_usd"] = 0 
                                else:
                                    token["total_value_usd"] = token_balance * token_price
                                
                                filtered_tokens.append(token)
                            # else:
                            #     print(f"🚫 Filtrelenen token: {token.get('symbol')} - Geçersiz token")
                    
                    # Filtrelenmiş token listesini güncelle
                    wallet_result["tokens"] = filtered_tokens

            return wallet_results


    def fetch_address_tokens(chain, address):
        chain_name = {
            1: "eth-mainnet",
            11155111: "eth-sepolia",
            137: "polygon-mainnet",
            42161: "arb-mainnet",
            56: "bnb-mainnet",
            97: "bnb-testnet"
        }.get(chain)

        if not chain_name:
            raise ValueError(f"Bilinmeyen chain: {chain}")

        url = f"https://{chain_name}.g.alchemy.com/v2/{RPC_KEY}"
        headers = {'Content-Type': 'application/json'}

        token_data = []

        # 1. Native Token Bakiyesi
        try:
            native_balance_req = {
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "latest"],
                "id": 10
            }
            native_res = requests.post(url, headers=headers, json=native_balance_req, timeout=10).json()
            native_balance = int(native_res.get("result", "0x0"), 16) / 1e18

            if native_balance > 0:
                native_symbol = {
                    1: "ETH",
                    11155111: "ETH",        # SepoliaETH yerine ETH kullan (fiyat için)
                    137: "MATIC",
                    42161: "ETH",
                    56: "BNB",
                    97: "BNB"               # tBNB yerine BNB kullan (fiyat için)
                }.get(chain, "NATIVE")

                token_data.append({
                    "symbol": native_symbol,
                    "name": native_symbol,
                    "contractAddress": None,
                    "balance": native_balance,
                    "logo": None,
                    "isNative": True
                })
        except Exception as e:
            print(f"Native token alınırken hata: {e}")

        # 2. ERC-20 Token Bakiyeleri
        try:
            data = {
                "jsonrpc": "2.0",
                "method": "alchemy_getTokenBalances",
                "params": [address],
                "id": 1
            }
            balance_res = requests.post(url, headers=headers, json=data, timeout=10).json()
            balances = balance_res.get("result", {}).get("tokenBalances", [])
        except Exception as e:
            print(f"Token bakiyeleri alınırken hata: {e}")
            return token_data  # sadece native varsa onu döner

        for token in balances:
            try:
                metadata_req = {
                    "jsonrpc": "2.0",
                    "method": "alchemy_getTokenMetadata",
                    "params": [token["contractAddress"]],
                    "id": 2
                }
                meta_res = requests.post(url, headers=headers, json=metadata_req, timeout=10).json()
                metadata = meta_res.get("result", {})
                decimals = metadata.get("decimals", 18)
                actual_balance = int(token["tokenBalance"], 16) / (10 ** decimals)
                if actual_balance == 0:
                    continue
                symbol = metadata.get("symbol", "UNKNOWN")
                name = metadata.get("name", "UNKNOWN")
                logo = metadata.get("logo", None)
                token_data.append({
                    "symbol": symbol,
                    "name": name,
                    "contractAddress": token["contractAddress"],
                    "balance": actual_balance,
                    "logo": logo,
                    "isNative": False
                })
            except Exception as e:
                print(f"Metadata hatası: {e}")
                continue

        return token_data

    def get_token_prices_from_cmc(symbols):
        all_results = {}
        # valid_tokens = set()  # Geçerli tokenları takip etmek için

        # Cache temizliği (sadece tarih farklıysa)
        price_cache.cleanup_old_cache()

        # Native token'ları CMC'deki doğru sembollerle eşle
        NATIVE_CMC_MAPPING = {
            "SepoliaETH": "ETH",  # Sepolia testnet ETH'i gerçek ETH fiyatıyla eşle
            "tBNB": "BNB",        # Testnet BNB'yi gerçek BNB fiyatıyla eşle
            "MATIC": "MATIC",     # Polygon MATIC
            "ETH": "ETH",         # Ethereum
            "BNB": "BNB"          # Binance Coin
        }

        # Sembolleri CMC formatına çevir
        symbol_mapping = {}  # original -> cmc mapping
        for symbol in symbols:
            cmc_symbol = NATIVE_CMC_MAPPING.get(symbol, symbol)
            symbol_mapping[symbol] = cmc_symbol

        symbols_to_fetch = []
        # Önce cache'den al (sadece native token olmayanlar için)
        for symbol in symbols:
            cmc_symbol = symbol_mapping[symbol]
            
            # Native token ise cache'den alma, her zaman API'den al
            if cmc_symbol in NATIVE_CMC_MAPPING.values():
                symbols_to_fetch.append(symbol)
                # valid_tokens.add(symbol.lower())  # Native tokenlar her zaman geçerli
            else:
                cached = price_cache.get_cached_price_by_symbol(cmc_symbol)
                if cached:
                    all_results[symbol.lower()] = cached
                    # valid_tokens.add(symbol.lower())  # Cache'den gelen tokenlar geçerli kabul edilir
                else:
                    symbols_to_fetch.append(symbol)

        if symbols_to_fetch:
            print(f"API'den alınacak tokenler: {symbols_to_fetch}")
            url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
            headers = {
                "Accepts": "application/json",
                "X-CMC_PRO_API_KEY": CMC_API_KEY
            }

            # CMC sembollerini al ve unique yap
            cmc_symbols_to_fetch = [symbol_mapping[symbol] for symbol in symbols_to_fetch]
            unique_cmc_symbols = list(set(cmc_symbols_to_fetch))

            symbols_chunks = [unique_cmc_symbols[i:i + 10] for i in range(0, len(unique_cmc_symbols), 10)]
            print(f"CMC Symbol chunk'lari: {symbols_chunks}")

            for chunk in symbols_chunks:
                params = {
                    "symbol": ",".join(chunk),
                    "convert": "USD"
                }
                try:
                    response = requests.get(url, headers=headers, params=params, timeout=10)
                    if response.status_code == 200:
                        data = response.json()["data"]
                        print(f"CMC API'den {len(data)} token bilgisi alindi.")

                        # Her original symbol için fiyat bilgisini ata
                        for original_symbol in symbols_to_fetch:
                            cmc_symbol = symbol_mapping[original_symbol]

                            if cmc_symbol in data:
                                token_data = data[cmc_symbol]
                                
                                # Native token ise veya geçerli token ise işle
                                # if (cmc_symbol in NATIVE_CMC_MAPPING.values() or is_valid_token(token_data)):
                                    
                                price_info = {
                                    "usd": token_data["quote"]["USD"]["price"],
                                    "market_cap": token_data["quote"]["USD"].get("market_cap", 0),
                                    "percent_change_24h": token_data["quote"]["USD"].get("percent_change_24h", 0)
                                }
                                all_results[original_symbol.lower()] = price_info
                                # valid_tokens.add(original_symbol.lower())
                                # Sadece native değilse ve fiyat bilgisi varsa cache'e kaydet
                                if (
                                    cmc_symbol not in NATIVE_CMC_MAPPING.values() and
                                    price_info["usd"] not in (None, 0)
                                ):
                                    price_cache.set_cached_price_by_symbol(cmc_symbol, price_info)
                                # else:
                                #     print(f"🚫 Token filtrelendi: {cmc_symbol} (original: {original_symbol}) - Geçersiz token")
                            else:
                                print(f"Token bulunamadı: {cmc_symbol} (original: {original_symbol})")
                    else:
                        print(f"CMC API hata: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f"CMC API hatasi: {e}")

                time.sleep(1)

        print(f"Toplam sonuç sayısı: {len(all_results)}")
        # print(f"Geçerli token sayısı: {len(valid_tokens)}")
        return all_results
    
    def price(price: PriceDto):
        print(f"Price endpoint called with: {price}")
        url = "https://router.gluex.xyz/v1/quote"

        payload = {
            "chainID": price.chainID,
            "inputToken": price.inputToken,
            "outputToken": price.outputToken,
            "inputAmount": price.inputAmount,
            "userAddress": price.userAddress,
            "outputReceiver": price.userAddress,
            "slippage": price.slippage ,
            "uniquePID": "866a61811189692e8eccae5d2759724a812fa6f8703ebffe90c29dc1f886bbc1",
            "isPermit2": False,
            "computeStable": True,
            "computeEstimate": True,
            "activateSurplusFee": False

            
        }
        print(payload)
        headers = {
            "Content-Type": "application/json", 
            "Accept": "*/*",
            "x-api-key": f"VtQwnrPU75cMIFFquIbZpiIyxFL0siqf",
            "Origin": "https://dapp.gluex.xyz",
            "Referer": "https://dapp.gluex.xyz/"
        }

        response = requests.post(url, json=payload, headers=headers)
        print(f"Swap API response status: {response.status_code}")
        print(f"Swap API response text: {response.text}")
        response_data = response.json()
        if response.status_code != 200:
            return {
                "status": response.status_code,
                "result": {
                    "error": response_data
                }
            }
        if response_data.get("statusCode") != 200:
            print(f"Swap API beklenmeyen yanıt: {response_data}")
            return {
                "status": response_data.get("statusCode", 500),
                "result": {
                    "error": response_data.get("error", "Unknown error")
                }
            }
        result =response_data['result']
        transaction = {
            "inputAmount": result["inputAmount"],
            "outputAmount": result["outputAmount"],
            "effectiveInputAmount": result["effectiveInputAmount"],
            "effectiveOutputAmount": result["effectiveOutputAmount"],
            "minOutputAmount": result["minOutputAmount"],
            "inputAmountUSD": result["inputAmountUSD"],
            "outputAmountUSD": result["outputAmountUSD"],
            "effectiveInputAmountUSD": result["effectiveInputAmountUSD"], 
            "effectiveOutputAmountUSD": result["effectiveOutputAmountUSD"],
            "estimatedNetSurplus": result["estimatedNetSurplus"],
            "to": result["router"],
            "data": result["calldata"],
            "value": hex(int(result["value"])),
            "gasLimit": result.get("computationUnits", 2000000),
            "gasPrice": result.get("gasPrice")
        }
        response={
            "status": response.json()["statusCode"],
            "result": transaction,
        }

        return response