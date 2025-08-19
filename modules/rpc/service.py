from datetime import datetime
from dotenv import load_dotenv
import requests
import time
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.rpc.dto.rpcDto import rpcDTO
from modules.rpc.dto.swapDto import SwapDto 
from modules.rpc.dto.priceDto import PriceDto

load_dotenv()
# RPC ve API anahtarlarını .env dosyasından al
RPC_KEY = os.getenv("RPC_KEY")
if not RPC_KEY:
    raise ValueError("RPC_KEY environment variable is not set. Please set it in the .env file.")

COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
if not COINGECKO_API_KEY:
    raise ValueError("COINGECKO_API_KEY environment variable is not set. Please set it in the .env file.")

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

# CoinGecko platform mapping
COINGECKO_PLATFORM_MAPPING = {
    1: "ethereum",
    11155111: "ethereum",  # Sepolia testnet
    137: "polygon-pos",
    42161: "arbitrum-one",
    56: "binance-smart-chain",
    97: "binance-smart-chain"  # BSC testnet
}

# CoinGecko native token IDs
COINGECKO_NATIVE_IDS = {
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "MATIC": "matic-network",
    "AVAX": "avalanche-2"
}

class SimpleTokenCache:
    def __init__(self):
        self.cache_file = "token_cache.json"
        self.cache = self.load_cache()
        self.cache_loaded = False
    
    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                
                today = datetime.now().strftime('%Y-%m-%d')
                
                if data.get('date') != today:
                    return {
                        'date': today, 
                        'tokens': {},
                        'not_found': {}, 
                        'invalid_trust': {}  
                    }
                
                if 'not_found' not in data:
                    data['not_found'] = {}
                if 'invalid_trust' not in data:
                    data['invalid_trust'] = {}
                
                return data
            except Exception as e:
                print(f"Cache yükleme hatası: {e}")
        
        today = datetime.now().strftime('%Y-%m-%d')
        return {
            'date': today, 
            'tokens': {},
            'not_found': {},
            'invalid_trust': {}
        }
    
    def save_cache(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"Cache kaydetme hatası: {e}")
    
    def get_cached_price_by_symbol(self, symbol):
        cached_data = self.cache['tokens'].get(symbol.lower())
        return cached_data
    
    def get_cached_price_by_contract(self, contract_address):
        cached_data = self.cache['tokens'].get(f"contract_{contract_address.lower()}")
        return cached_data
    
    def is_token_not_found(self, contract_address):
        return contract_address.lower() in self.cache['not_found']
    
    def is_token_invalid_trust(self, contract_address):
        return contract_address.lower() in self.cache['invalid_trust']
    
    def set_cached_price_by_symbol(self, symbol, price_info):
        self.cache['tokens'][symbol.lower()] = price_info
        self.save_cache()
    
    def set_cached_price_by_contract(self, contract_address, price_info):
        self.cache['tokens'][f"contract_{contract_address.lower()}"] = price_info
        self.save_cache()
    
    def mark_token_not_found(self, contract_address, token_symbol=""):
        self.cache['not_found'][contract_address.lower()] = {
            'timestamp': datetime.now().isoformat(),
            'symbol': token_symbol
        }
        self.save_cache()
        print(f"🚫 Cache'e eklendi (bulunamadı): {token_symbol} ({contract_address})")
    
    def mark_token_invalid_trust(self, contract_address, token_symbol="", trust_info=""):
        self.cache['invalid_trust'][contract_address.lower()] = {
            'timestamp': datetime.now().isoformat(),
            'symbol': token_symbol,
            'trust_info': trust_info
        }
        self.save_cache()
    
    def cleanup_old_cache(self):
        today = datetime.now().strftime('%Y-%m-%d')
        if self.cache.get('date') != today:
            self.cache = {
                'date': today, 
                'tokens': {},
                'not_found': {},
                'invalid_trust': {}
            }
            self.save_cache()
    
    def get_cache_stats(self):
        return {
            'valid_tokens': len(self.cache['tokens']),
            'not_found': len(self.cache['not_found']),
            'invalid_trust': len(self.cache['invalid_trust']),
            'date': self.cache['date']
        }

price_cache = SimpleTokenCache()

def get_coingecko_price_by_contract(platform, contract_address):
    url = f"https://api.coingecko.com/api/v3/coins/{platform}/contract/{contract_address}"
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": COINGECKO_API_KEY
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            tickers = data.get("tickers", [])
            if tickers:
                green_count = sum(1 for ticker in tickers if ticker.get("trust_score") == "green")
                total_count = len(tickers)
                trust_info = f"{green_count}/{total_count} green"
                

                if green_count <= total_count / 2:
                    print(f"Trust score yetersiz: {trust_info}")
                    return None, "invalid_trust", trust_info
            
            market_data = data.get("market_data", {})
            
            if market_data:
                current_price = market_data.get("current_price", {})
                market_cap = market_data.get("market_cap", {})
                price_change_24h = market_data.get("price_change_percentage_24h")
                
                result = {
                    "usd": current_price.get("usd", 0),
                    "market_cap": market_cap.get("usd", 0),
                    "percent_change_24h": price_change_24h or 0,
                    "symbol": data.get("symbol", "UNKNOWN").upper(),
                    "name": data.get("name", "UNKNOWN"),
                    "logo": data.get("image", {}).get("small"),
                    "decimals": data.get("detail_platforms", {}).get(platform, {}).get("decimal_place", 18)
                }
                
                return result, "success", ""
        
        elif response.status_code == 404:
            return None, "not_found", "Token not found in CoinGecko"
        
    except Exception as e:
        print(f"CoinGecko contract API hatası: {e}")
    
    return None, "error", "API request failed"

def get_coingecko_price_by_ids(coin_ids):
    if not coin_ids:
        return {}
    
    url = "https://api.coingecko.com/api/v3/simple/price"
    headers = {
        "accept": "application/json",
        "x-cg-demo-api-key": COINGECKO_API_KEY
    }
    
    params = {
        "ids": ",".join(coin_ids),
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_change": "true"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = {}
            
            for coin_id, price_data in data.items():
                results[coin_id] = {
                    "usd": price_data.get("usd", 0),
                    "market_cap": price_data.get("usd_market_cap", 0),
                    "percent_change_24h": price_data.get("usd_24h_change", 0)
                }
            
            return results
    except Exception as e:
        print(f"CoinGecko simple price API hatası: {e}")
    
    return {}

class RPCService:
    def info(rpc_request: rpcDTO):
        wallet_results = []
        unique_tokens_by_contract = {}
        all_token_symbols = set()
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            address_to_future = {
                executor.submit(RPCService.fetch_address_tokens, rpc_request.chain, wallet_address): wallet_address 
                for wallet_address in rpc_request.addresses
            }
            
            for completed_future in as_completed(address_to_future):
                current_address = address_to_future[completed_future]
                
                try:
                    token_list = completed_future.result()
                    
                    wallet_results.append({
                        "address": current_address, 
                        "tokens": token_list
                    })
                    
                    for token_info in token_list:
                        token_symbol = token_info.get("symbol")
                        if token_symbol:
                            all_token_symbols.add(token_symbol)
                        contract_address = token_info.get("contractAddress")
                        if contract_address is not None:
                            normalized_address = contract_address.lower()
                            unique_tokens_by_contract[normalized_address] = token_info
                            
                except Exception as error:
                    print(f"❌ Hata - Cüzdan adresi {current_address}: {error}")

            if unique_tokens_by_contract or all_token_symbols:
                native_prices = RPCService.get_native_token_prices(all_token_symbols)
                contract_prices, valid_contract_tokens = RPCService.get_token_prices_from_coingecko(
                    rpc_request.chain, unique_tokens_by_contract
                )
                all_prices = {**native_prices, **contract_prices}
                all_valid_tokens = set(native_prices.keys()) | valid_contract_tokens
                
                for wallet_result in wallet_results:
                    filtered_tokens = []
                    for token in wallet_result["tokens"]:
                        token_symbol = token.get("symbol", "").lower()
                        contract_address = token.get("contractAddress")
                        
                        price_data = None
                        is_valid_token = False
                        
                        if token.get("isNative", False) and token_symbol in all_valid_tokens:
                            price_data = all_prices.get(token_symbol, {})
                            is_valid_token = True
                        elif contract_address:
                            contract_key = f"contract_{contract_address.lower()}"
                            price_data = all_prices.get(contract_key, {})
                            if price_data:
                                is_valid_token = True
                        
                        if price_data and is_valid_token:
                            if "symbol" in price_data and price_data["symbol"] != "UNKNOWN":
                                token["symbol"] = price_data["symbol"]
                            if "name" in price_data and price_data["name"] != "UNKNOWN":
                                token["name"] = price_data["name"]
                            if "logo" in price_data and price_data["logo"]:
                                token["logo"] = price_data["logo"]
                            if "decimals" in price_data:
                                old_decimals = 18
                                new_decimals = price_data["decimals"]
                                if new_decimals != old_decimals:
                                    token["balance"] = token["balance"] * (10 ** old_decimals) / (10 ** new_decimals)
                            
                            token["price_usd"] = price_data.get("usd", 0)
                            token["price_change_24h"] = price_data.get("percent_change_24h", 0)
                            token["market_cap"] = price_data.get("market_cap", 0)
                            
                            token_balance = token.get("balance", 0)
                            token_price = token.get("price_usd", 0)
                            if token_price is None:
                                token["total_value_usd"] = 0 
                            else:
                                token["total_value_usd"] = token_balance * token_price
                            
                            filtered_tokens.append(token)
                    wallet_result["tokens"] = filtered_tokens

            return wallet_results

    def get_native_token_prices(symbols):
        results = {}
        price_cache.cleanup_old_cache()
        native_ids_to_fetch = []
        symbol_to_id_mapping = {}
        
        for symbol in symbols:
            if symbol.upper() in COINGECKO_NATIVE_IDS:
                coin_id = COINGECKO_NATIVE_IDS[symbol.upper()]
                symbol_to_id_mapping[symbol.lower()] = coin_id
                
                # Cache'den kontrol et
                cached = price_cache.get_cached_price_by_symbol(symbol)
                if cached:
                    results[symbol.lower()] = cached
                else:
                    native_ids_to_fetch.append(coin_id)
        if native_ids_to_fetch:
            coin_prices = get_coingecko_price_by_ids(native_ids_to_fetch)
            
            for symbol, coin_id in symbol_to_id_mapping.items():
                if coin_id in coin_prices and symbol not in results:
                    price_data = coin_prices[coin_id]
                    results[symbol] = price_data
                    price_cache.set_cached_price_by_symbol(symbol, price_data)
        
        return results

    def get_token_prices_from_coingecko(chain_id, tokens_by_contract):
        all_results = {}
        valid_tokens = set()
        
        platform = COINGECKO_PLATFORM_MAPPING.get(chain_id)
        if not platform:
            return all_results, valid_tokens

        api_calls_made = 0
        skipped_from_cache = 0
        
        for contract_address, token_info in tokens_by_contract.items():
            token_symbol = token_info.get("symbol", "UNKNOWN")
            
            cached = price_cache.get_cached_price_by_contract(contract_address)
            if cached:
                contract_key = f"contract_{contract_address}"
                all_results[contract_key] = cached
                valid_tokens.add(cached.get("symbol", token_symbol).lower())
                skipped_from_cache += 1
                continue

            if price_cache.is_token_not_found(contract_address):
                skipped_from_cache += 1
                continue
            
            if price_cache.is_token_invalid_trust(contract_address):
                skipped_from_cache += 1
                continue

            price_data, status, info = get_coingecko_price_by_contract(platform, contract_address)
            api_calls_made += 1
            
            if status == "success" and price_data:
                contract_key = f"contract_{contract_address}"
                all_results[contract_key] = price_data
                valid_tokens.add(price_data.get("symbol", token_symbol).lower())
                
                price_cache.set_cached_price_by_contract(contract_address, price_data)
                
                
            elif status == "not_found":
                price_cache.mark_token_not_found(contract_address, token_symbol)
                
            elif status == "invalid_trust":
                price_cache.mark_token_invalid_trust(contract_address, token_symbol, info)
            
        return all_results, valid_tokens

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
                    11155111: "ETH",
                    137: "MATIC",
                    42161: "ETH",
                    56: "BNB",
                    97: "BNB"
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
            return token_data

        for token in balances:
            try:
                balance_hex = token.get("tokenBalance", "0x0")
                if balance_hex == "0x0":
                    continue
                
                actual_balance = int(balance_hex, 16) / (10 ** 18)
                if actual_balance == 0:
                    continue
                
                # Placeholder bilgiler - CoinGecko'dan güncellenecek
                token_data.append({
                    "symbol": "UNKNOWN",  # CoinGecko'dan güncellenecek
                    "name": "UNKNOWN",    # CoinGecko'dan güncellenecek
                    "contractAddress": token["contractAddress"],
                    "balance": actual_balance,
                    "logo": None,         # CoinGecko'dan güncellenecek
                    "isNative": False
                })
            except Exception as e:
                print(f"Token bakiye hatası: {e}")
                continue

        return token_data
    
    def price(price: PriceDto):
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
        
        headers = {
            "Content-Type": "application/json", 
            "Accept": "*/*",
            "x-api-key": f"VtQwnrPU75cMIFFquIbZpiIyxFL0siqf",
            "Origin": "https://dapp.gluex.xyz",
            "Referer": "https://dapp.gluex.xyz/"
        }

        response = requests.post(url, json=payload, headers=headers)
        response_data = response.json()
        if response.status_code != 200:
            return {
                "status": response.status_code,
                "result": {
                    "error": response_data
                }
            }
        if response_data.get("statusCode") != 200:
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

    def swap(swap: SwapDto):
        url = "https://router.gluex.xyz/v1/quote"

        payload = {
            "chainID": swap.chainID,
            "inputToken": swap.inputToken,
            "outputToken": swap.outputToken,
            "inputAmount": swap.inputAmount,
            "userAddress": swap.userAddress,
            "outputReceiver": swap.userAddress,
            "slippage": swap.slippage,
            "uniquePID": "866a61811189692e8eccae5d2759724a812fa6f8703ebffe90c29dc1f886bbc1"
        }
        headers = {
            "Content-Type": "application/json", 
            "Accept": "*/*",
            "x-api-key": f"VtQwnrPU75cMIFFquIbZpiIyxFL0siqf",
            "Origin": "https://dapp.gluex.xyz",
            "Referer": "https://dapp.gluex.xyz/"
        }

        response = requests.post(url, json=payload, headers=headers)

        response_data = response.json()
        if response.status_code != 200:
            return {
                "status": response.status_code,
                "result": {
                    "error": response_data
                }
            }
        if response_data.get("statusCode") != 200:
            return {
                "status": response_data.get("statusCode", 500),
                "result": {
                    "error": response_data.get("error", "Unknown error")
                }
            }
        return response_data