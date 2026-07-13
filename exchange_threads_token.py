import os
import requests
from dotenv import load_dotenv

def main():
    # Load env path relative to script
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path=env_path)
    
    short_token = os.getenv("THREADS_ACCESS_TOKEN")
    
    print("=== THREADS TOKEN EXCHANGER (SHORT-LIVED TO LONG-LIVED) ===")
    print("Masa aktif token bawaan (short-lived) hanya 1 jam. Script ini akan menukarnya menjadi 60 hari.")
    print("-----------------------------------------------------------")
    
    if not short_token or short_token.startswith("your-"):
        short_token = input("Masukkan Short-Lived Threads Access Token Anda: ").strip()
    else:
        print(f"Ditemukan token di .env: {short_token[:15]}...{short_token[-10:]}")
        use_env = input("Gunakan token dari .env ini? (y/n): ").strip().lower()
        if use_env != 'y':
            short_token = input("Masukkan Short-Lived Threads Access Token yang baru: ").strip()
        
    app_secret = input("Masukkan Threads App Secret (Client Secret dari Meta Developer Dashboard): ").strip()
    
    if not short_token or not app_secret:
        print("❌ Token dan App Secret wajib diisi!")
        return

    url = "https://graph.threads.net/access_token"
    params = {
        "grant_type": "th_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token
    }
    
    print("\nMengirim permintaan penukaran token ke Threads API...")
    try:
        r = requests.get(url, params=params)
        res = r.json()
        
        if "access_token" in res:
            long_token = res["access_token"]
            expires_in = res.get("expires_in", 0)
            days = expires_in / 86400
            
            print(f"\n[SUKSES] Berhasil menukar ke Long-Lived Token!")
            print(f"Masa Berlaku: {days:.1f} hari ({expires_in} detik)")
            print(f"\nLong-Lived Token Anda:\n{long_token}\n")
            
            update_env = input("Apakah Anda ingin memperbarui file .env secara otomatis? (y/n): ").strip().lower()
            if update_env == 'y':
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    updated = False
                    for i, line in enumerate(lines):
                        if line.startswith("THREADS_ACCESS_TOKEN="):
                            lines[i] = f"THREADS_ACCESS_TOKEN={long_token}\n"
                            updated = True
                            break
                            
                    if not updated:
                        lines.append(f"\nTHREADS_ACCESS_TOKEN={long_token}\n")
                        
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    print("[SUCCESS] File .env berhasil diperbarui dengan Long-Lived Token baru!")
                else:
                    print("[WARNING] File .env tidak ditemukan, silakan salin token di atas secara manual.")
        else:
            print(f"[FAIL] Gagal menukar token. Respon API: {res}")
            
    except Exception as e:
        print(f"[FAIL] Terjadi kesalahan koneksi API: {e}")

if __name__ == "__main__":
    main()
