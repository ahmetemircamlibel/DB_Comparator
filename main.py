import sqlalchemy
from sqlalchemy import create_engine, inspect, text
import pandas as pd
import os
import sys
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Konfigürasyon
# Öncelik: DB1_URL / DB2_URL. Yoksa: STAGE_DB_URL / SANDBOX_DB_URL. Yoksa: Demo SQLite.
DB1_URL = os.getenv('DB1_URL') or os.getenv('STAGE_DB_URL') or 'sqlite:///stage_demo.db'
DB2_URL = os.getenv('DB2_URL') or os.getenv('SANDBOX_DB_URL') or 'sqlite:///sandbox_demo.db'

# Raporlarda görünecek isimler
DB1_NAME = os.getenv('DB1_NAME', 'DB1')
DB2_NAME = os.getenv('DB2_NAME', 'DB2')

# Eğer eski env değişkenleri kullanılıyorsa ve isim belirtilmemişse, mantıklı varsayılanlar ata
if not os.getenv('DB1_NAME') and os.getenv('STAGE_DB_URL'):
    DB1_NAME = 'Stage'
if not os.getenv('DB2_NAME') and os.getenv('SANDBOX_DB_URL'):
    DB2_NAME = 'Sandbox'

def get_db_engine(url):
    try:
        engine = create_engine(url)
        return engine
    except Exception as e:
        print(f"Hata: {url} adresine bağlanılamadı. {e}")
        return None

def find_definition_tables(engine):
    """
    Veritabanındaki tüm şemaları ve tabloları tarar.
    Yeni Kriterler (Son Güncelleme):
    1. İçinde 'org_id', 'sube_id' (veya 'şube_id') VEYA 'kul_sirket_id' kolonlarından en az biri olmalı.
    2. Bu kolonlar haricinde '_id' ile biten başka kolon OLMAMALI.
    """
    inspector = inspect(engine)
    candidate_tables = []
    rejected_tables = []
    
    try:
        all_schemas = inspector.get_schema_names()
        # Sistem şemalarını hariç tut
        schemas = [s for s in all_schemas if s not in ['information_schema', 'pg_catalog']]
    except Exception as e:
        print(f"Şema listesi alınamadı (Varsayılan şema kullanılacak): {e}")
        schemas = [None] # Varsayılan şema

    print(f"Taranacak Şemalar: {schemas}")

    for schema in schemas:
        try:
            table_names = inspector.get_table_names(schema=schema)
        except Exception as e:
            print(f"Uyarı: Şema '{schema}' okunamadı: {e}")
            continue

        for table_name in table_names:
            try:
                columns = inspector.get_columns(table_name, schema=schema)
                col_names = [col['name'].lower() for col in columns]
                
                # Kriter 1: 'org_id', 'sube_id' veya 'kul_sirket_id' (en az biri)
                has_org = 'org_id' in col_names
                has_sube = 'sube_id' in col_names or 'şube_id' in col_names
                has_kul_sirket = 'kul_sirket_id' in col_names
                
                if not (has_org or has_sube or has_kul_sirket):
                    rejected_tables.append({
                        'schema': schema,
                        'table': table_name,
                        'reason': "org_id, sube_id veya kul_sirket_id YOK"
                    })
                    continue

                # Kriter 2: Yasaklı _id kontrolü
                # İzin verilenler: org_id, sube_id, şube_id, kul_sirket_id
                allowed_ids = ['org_id', 'sube_id', 'şube_id', 'kul_sirket_id']
                
                has_forbidden_id = False
                forbidden_col = ""
                for col in col_names:
                    if col.endswith('_id') and col not in allowed_ids:
                        has_forbidden_id = True
                        forbidden_col = col
                        break
                
                if has_forbidden_id:
                    rejected_tables.append({
                        'schema': schema,
                        'table': table_name,
                        'reason': f"Yasaklı kolon var: {forbidden_col}"
                    })
                    continue

                # Tüm kriterleri geçti
                candidate_tables.append({
                    'schema': schema,
                    'table_name': table_name,
                    'full_name': f"{schema}.{table_name}" if schema else table_name,
                    'reason': "Kriterlere uygun (org/sube/kul_sirket id var, yasaklı _id yok)"
                })

            except Exception as e:
                # print(f"Warning: {table_name} kolonları okunamadı: {e}")
                pass

    return candidate_tables, rejected_tables

def compare_tables(db1_engine, db2_engine, common_tables_list, db1_name, db2_name, base_db='SYMMETRIC'):
    """
    Ortak tabloları iki DB arasında karşılaştırır.
    base_db: 'DB1', 'DB2' veya 'SYMMETRIC'
    """
    results = []

    # Base DB'ye göre hedef DB ismini belirle (Raporlama için)
    target_db_name = db2_name if base_db == 'DB1' else db1_name if base_db == 'DB2' else "Diğer"

    for item in common_tables_list:
        schema = item['schema']
        table_name = item['table_name']
        full_name = item['full_name']
        
        print(f"\nKarşılaştırılıyor: {full_name}")

        # Varsayılan değerler
        res = {
            'Şema': schema if schema else 'default',
            'Tablo': table_name,
            'Durum': '?',
            'Açıklama': '-',
            f'{db1_name} Satır': 0,
            f'{db2_name} Satır': 0,
            'Fark (Adet)': 0,
            'Eksik Kayıt': 0, 
            'Fazla Kayıt': 0,
            f'Sadece {db1_name}': 0,
            f'Sadece {db2_name}': 0,
            'Notlar': ''
        }

        try:
            # Verileri çek
            if schema:
                query = f"SELECT * FROM {schema}.{table_name}"
            else:
                query = f"SELECT * FROM {table_name}"
            
            # GÜVENLİK KONTROLÜ
            dangerous_keywords = ['DELETE', 'DROP', 'UPDATE', 'INSERT', 'TRUNCATE', 'ALTER', 'GRANT', 'REVOKE']
            query_upper = query.upper()
            if not query_upper.strip().startswith('SELECT'):
                raise ValueError("Güvenlik Hatası: Sadece SELECT sorgularına izin verilir.")
            
            if ';' in table_name or (schema and ';' in schema):
                 raise ValueError(f"Güvenlik Hatası: İsimde geçersiz karakter (;)")

            # Pandas ile okuma
            df_db1 = pd.read_sql(query, db1_engine)
            df_db2 = pd.read_sql(query, db2_engine)

            # Satır sayıları
            count_db1 = len(df_db1)
            count_db2 = len(df_db2)
            
            res[f'{db1_name} Satır'] = count_db1
            res[f'{db2_name} Satır'] = count_db2

            if df_db1.equals(df_db2):
                res['Durum'] = "EŞİT"
                res['Açıklama'] = "Veriler Birebir Aynı"
                res['Fark (Adet)'] = 0
            else:
                res['Durum'] = "FARKLI"
                
                # Detaylı fark analizi
                common_cols = list(set(df_db1.columns) & set(df_db2.columns))
                
                key_col = None
                possible_keys = ['id', 'kod', 'code', 'uuid', 'plaka'] 
                for k in possible_keys:
                    if k in [c.lower() for c in common_cols]:
                        for orig_col in common_cols:
                            if orig_col.lower() == k:
                                key_col = orig_col
                                break
                        if key_col: break
                
                if key_col:
                    merged = df_db1.merge(df_db2, on=key_col, how='outer', suffixes=('_db1', '_db2'), indicator=True)
                    
                    only_db1 = merged[merged['_merge'] == 'left_only']
                    only_db2 = merged[merged['_merge'] == 'right_only']
                    
                    # Kolon isimlerini düzelt (suffixleri kaldır veya orjinal df'den al)
                    # Merge sonrası _db1, _db2 suffixli kolonlar oluşur. 
                    # SQL üretirken orjinal veriyi kullanmak daha temiz.
                    # only_db1 için df_db1'den, only_db2 için df_db2'den veriyi filtreleyip alabiliriz.
                    
                    # Basitçe ID'leri alıp orjinal DF'den filtreleyelim
                    ids_only_db1 = only_db1[key_col].tolist()
                    ids_only_db2 = only_db2[key_col].tolist()
                    
                    data_only_db1 = df_db1[df_db1[key_col].isin(ids_only_db1)]
                    data_only_db2 = df_db2[df_db2[key_col].isin(ids_only_db2)]

                    cnt_db1 = len(data_only_db1)
                    cnt_db2 = len(data_only_db2)
                    
                    res[f'Sadece {db1_name}'] = cnt_db1
                    res[f'Sadece {db2_name}'] = cnt_db2
                    res['Fark (Adet)'] = cnt_db1 + cnt_db2
                    res['Notlar'] = f"Anahtar: {key_col}"

                    # Base DB Mantığına Göre Açıklama
                    if base_db == 'SYMMETRIC':
                        if cnt_db1 == 0 and cnt_db2 == 0:
                            res['Açıklama'] = "Satır Sayıları Eşit Ancak İçerik Farklı"
                        else:
                            res['Açıklama'] = f"{db1_name}'de {cnt_db1}, {db2_name}'de {cnt_db2} adet farklı kayıt"
                    
                    elif base_db == 'DB1':
                        # Base: DB1. Hedef: DB2.
                        res['Eksik Kayıt'] = cnt_db1
                        res['Fazla Kayıt'] = cnt_db2
                        
                        if cnt_db1 == 0 and cnt_db2 == 0:
                            res['Açıklama'] = "Satır Sayıları Eşit Ancak İçerik Farklı"
                        else:
                            parts = []
                            if cnt_db1 > 0: parts.append(f"{target_db_name}'de {cnt_db1} adet EKSİK")
                            if cnt_db2 > 0: parts.append(f"{target_db_name}'de {cnt_db2} adet FAZLA")
                            res['Açıklama'] = ", ".join(parts)

                    elif base_db == 'DB2':
                        # Base: DB2. Hedef: DB1.
                        res['Eksik Kayıt'] = cnt_db2
                        res['Fazla Kayıt'] = cnt_db1
                        
                        if cnt_db1 == 0 and cnt_db2 == 0:
                            res['Açıklama'] = "Satır Sayıları Eşit Ancak İçerik Farklı"
                        else:
                            parts = []
                            if cnt_db2 > 0: parts.append(f"{target_db_name}'de {cnt_db2} adet EKSİK")
                            if cnt_db1 > 0: parts.append(f"{target_db_name}'de {cnt_db1} adet FAZLA")
                            res['Açıklama'] = ", ".join(parts)
                            
                else:
                    res['Açıklama'] = "Karşılaştırma Yapılamadı (Ortak Anahtar Yok)"
                    res['Notlar'] = "Ortak ID/Kod kolonu bulunamadı."

        except Exception as e:
            res['Durum'] = "HATA"
            res['Açıklama'] = "İşlem Hatası"
            res['Notlar'] = str(e)
            print(f"Hata oluştu {full_name}: {e}")
        
        results.append(res)

    return results

if __name__ == "__main__":
    print("--- Veritabanı Karşılaştırma Aracı ---")
    print("GÜVENLİK NOTU: Bu script veritabanı üzerinde SADECE OKUMA (SELECT) işlemi yapar.")
    
    # Kullanıcıdan DB bilgilerini iste (Varsayılanlar env'den veya globalden)
    print("\n--- Veritabanı Bağlantı Ayarları ---")
    print("Lütfen karşılaştırılacak veritabanı bilgilerini girin (Varsayılan için Enter'a basın):")
    
    # DB1
    db1_url_input = input(f"1. Veritabanı URL [{DB1_URL}]: ").strip()
    if db1_url_input: DB1_URL = db1_url_input
    
    db1_name_input = input(f"1. Veritabanı Görünen Adı [{DB1_NAME}]: ").strip()
    if db1_name_input: DB1_NAME = db1_name_input
    
    # DB2
    db2_url_input = input(f"2. Veritabanı URL [{DB2_URL}]: ").strip()
    if db2_url_input: DB2_URL = db2_url_input
    
    db2_name_input = input(f"2. Veritabanı Görünen Adı [{DB2_NAME}]: ").strip()
    if db2_name_input: DB2_NAME = db2_name_input

    # Demo veritabanı kontrolü (Eğer SQLite ve demo ise)
    if 'sqlite' in DB1_URL and 'demo' in DB1_URL and not os.path.exists('db1_demo.db') and not os.path.exists('stage_demo.db'):
         # Eski demo isimleri kalmış olabilir, basit kontrol
         pass

    print(f"\nAyarlar: {DB1_NAME} ({DB1_URL}) <--> {DB2_NAME} ({DB2_URL})")

    engine_db1 = get_db_engine(DB1_URL)
    engine_db2 = get_db_engine(DB2_URL)

    if not engine_db1 or not engine_db2:
        print("Veritabanı bağlantısı başarısız.")
        sys.exit(1)

    # 1. ADIM: Her iki DB'de Tanım Tablolarını Bul
    print("\n1. ADIM: Tanım Tabloları Taranıyor...")
    
    print(f"-> {DB1_NAME} taranıyor...")
    db1_candidates, db1_rejected = find_definition_tables(engine_db1)
    db1_map = {t['full_name']: t for t in db1_candidates}
    
    if not db1_candidates:
        print(f"UYARI: {DB1_NAME}'de kriterlere uyan tablo bulunamadı.")
        print("Reddedilenlerden bazı örnekler:")
        for r in db1_rejected[:10]:
            print(f" - {r['table']}: {r['reason']}")
    
    print(f"-> {DB2_NAME} taranıyor...")
    db2_candidates, db2_rejected = find_definition_tables(engine_db2)
    db2_map = {t['full_name']: t for t in db2_candidates}

    if not db2_candidates:
        print(f"UYARI: {DB2_NAME}'de kriterlere uyan tablo bulunamadı.")
        print("Reddedilenlerden bazı örnekler:")
        for r in db2_rejected[:10]:
            print(f" - {r['table']}: {r['reason']}")

def load_manual_tables_from_excel(file_path, db1_map, db2_map, engine_db1, engine_db2):
    """
    Excel dosyasından manuel eklenen tabloları okur ve map'lere ekler.
    """
    if not os.path.exists(file_path):
        return 0

    print(f"\nManuel tablo kontrolü: {file_path}")
    added_count = 0
    try:
        df_existing = pd.read_excel(file_path)
        df_existing.columns = [c.strip() for c in df_existing.columns]
        
        if 'Şema' in df_existing.columns and 'Tablo Adı' in df_existing.columns:
            insp1 = inspect(engine_db1)
            insp2 = inspect(engine_db2)
            
            for index, row in df_existing.iterrows():
                schema = row['Şema']
                table = row['Tablo Adı']
                
                if pd.isna(table): continue
                if pd.isna(schema): schema = None
                
                full_name = f"{schema}.{table}" if schema else table
                
                # Zaten listede varsa atla
                if full_name in db1_map or full_name in db2_map:
                    continue
                    
                # DB1 Kontrol
                exists_db1 = False
                try:
                    exists_db1 = insp1.has_table(table, schema=schema)
                except: pass
                
                if exists_db1:
                    print(f"  -> {DB1_NAME}'de BULUNDU ve EKLENDİ: {full_name}")
                    db1_map[full_name] = {
                        'schema': schema,
                        'table_name': table,
                        'full_name': full_name,
                        'reason': "Manuel Eklendi"
                    }
                    added_count += 1

                # DB2 Kontrol
                exists_db2 = False
                try:
                    exists_db2 = insp2.has_table(table, schema=schema)
                except: pass
                
                if exists_db2:
                    if not exists_db1: print(f"  -> {DB2_NAME}'de BULUNDU ve EKLENDİ: {full_name}")
                    db2_map[full_name] = {
                        'schema': schema,
                        'table_name': table,
                        'full_name': full_name,
                        'reason': "Manuel Eklendi"
                    }
                    if not exists_db1: added_count += 1

    except Exception as e:
        print(f"HATA: Manuel dosya okunamadı: {e}")
    
    return added_count

if __name__ == "__main__":
    # ... (önceki kodlar aynı) ...
    # ... find_definition_tables çağrıları ...
    
    # --- MANUEL TABLO EKLEME (İlk Kontrol) ---
    load_manual_tables_from_excel("bulunan_tanim_tablolari.xlsx", db1_map, db2_map, engine_db1, engine_db2)
    # ---------------------------

    # Bulunan tüm tabloları listele ve raporla
    all_full_names = set(db1_map.keys()) | set(db2_map.keys())
    discovery_report = []
    
    for full_name in all_full_names:
        in_db1 = full_name in db1_map
        in_db2 = full_name in db2_map
        
        # Bilgileri herhangi bir taraftan al
        item = db1_map[full_name] if in_db1 else db2_map[full_name]
        
        reason_db1 = db1_map[full_name]['reason'] if in_db1 else "-"
        reason_db2 = db2_map[full_name]['reason'] if in_db2 else "-"

        discovery_report.append({
            'Şema': item['schema'] if item['schema'] else 'default',
            'Tablo Adı': item['table_name'],
            f'{DB1_NAME}': 'VAR' if in_db1 else 'YOK',
            f'{DB2_NAME}': 'VAR' if in_db2 else 'YOK',
            f'{DB1_NAME} Tespit Nedeni': reason_db1,
            f'{DB2_NAME} Tespit Nedeni': reason_db2
        })

    df_discovery = pd.DataFrame(discovery_report)
    # Kolon sırası
    disc_cols = ['Şema', 'Tablo Adı', f'{DB1_NAME}', f'{DB2_NAME}', f'{DB1_NAME} Tespit Nedeni', f'{DB2_NAME} Tespit Nedeni']
    # Mevcut kolonları filtrele (hata almamak için)
    final_disc_cols = [c for c in disc_cols if c in df_discovery.columns]
    df_discovery = df_discovery[final_disc_cols]
    
    file_discovery = "bulunan_tanim_tablolari.xlsx"
    try:
        df_discovery.to_excel(file_discovery, index=False)
        print(f"\nTablo keşif raporu '{file_discovery}' dosyasına kaydedildi.")
    except Exception as e:
        print(f"Rapor kaydedilemedi (Dosya açık olabilir): {e}")

    # KULLANICI SEÇİMİ: Base DB
    print("\n--- KARŞILAŞTIRMA MODU SEÇİMİ ---")
    print("NOT: Eğer 'bulunan_tanim_tablolari.xlsx' dosyasına yeni tablo eklediyseniz, şimdi kaydedin.")
    print(f"1. {DB1_NAME}'i Base Al ({DB2_NAME}'deki eksikleri/fazlaları göster)")
    print(f"2. {DB2_NAME}'i Base Al ({DB1_NAME}'deki eksikleri/fazlaları göster)")
    print("3. SİMETRİK (İki tarafı eşit karşılaştır - Varsayılan)")
    
    choice = input("Seçiminiz (1/2/3): ").strip()
    
    # --- MANUEL TABLO EKLEME (İkinci Kontrol - Kullanıcı Girdisinden Sonra) ---
    print("\nSon dakika eklenen manuel tablolar kontrol ediliyor...")
    new_added = load_manual_tables_from_excel("bulunan_tanim_tablolari.xlsx", db1_map, db2_map, engine_db1, engine_db2)
    if new_added > 0:
        print(f"-> {new_added} yeni manuel tablo eklendi.")
    # ---------------------------

    # 2. ADIM: Ortak Tabloları Belirle (Güncel Map'ler ile)
    common_full_names = list(set(db1_map.keys()) & set(db2_map.keys()))
    
    if not common_full_names:
        print("\nHer iki veritabanında da bulunan ortak bir tanım tablosu yok. Karşılaştırma yapılmayacak.")
        sys.exit(0)

    # Ortak tabloların detay listesini oluştur
    common_tables_list = [db1_map[fn] for fn in common_full_names]

    base_db = 'SYMMETRIC'
    if choice == '1':
        base_db = 'DB1'
        print(f">> Mod: {DB1_NAME} Base alındı. Hedef: {DB2_NAME}.")
    elif choice == '2':
        base_db = 'DB2'
        print(f">> Mod: {DB2_NAME} Base alındı. Hedef: {DB1_NAME}.")
    else:
        print(">> Mod: SİMETRİK Karşılaştırma.")

    print(f"\n2. ADIM: Ortak Tablolar Karşılaştırılıyor ({len(common_tables_list)} adet)...")
    comparison_results = compare_tables(engine_db1, engine_db2, common_tables_list, db1_name=DB1_NAME, db2_name=DB2_NAME, base_db=base_db)

    # ... (Raporlama kısmı aynı) ...

    # 3. ADIM: Farklılıkları Raporla
    df_results = pd.DataFrame(comparison_results)
    
    # Kolon sırasını Base DB'ye göre düzenle
    if base_db == 'SYMMETRIC':
        cols = ['Şema', 'Tablo', 'Durum', 'Açıklama', f'{DB1_NAME} Satır', f'{DB2_NAME} Satır', 'Fark (Adet)', f'Sadece {DB1_NAME}', f'Sadece {DB2_NAME}', 'Notlar']
    else:
        cols = ['Şema', 'Tablo', 'Durum', 'Açıklama', f'{DB1_NAME} Satır', f'{DB2_NAME} Satır', 'Fark (Adet)', 'Eksik Kayıt', 'Fazla Kayıt', 'Notlar']

    final_cols = [c for c in cols if c in df_results.columns]
    df_results = df_results[final_cols]

    print("\n--- SONUÇ ÖZETİ ---")
    print_cols = ['Şema', 'Tablo', 'Durum', 'Açıklama']
    if base_db != 'SYMMETRIC':
        print_cols.extend(['Eksik Kayıt', 'Fazla Kayıt'])
    else:
        print_cols.append('Fark (Adet)')
        
    print(df_results[print_cols].to_string(index=False))
    


    file_diff = "veri_farkliliklari.xlsx"
    file_diff = "veri_farkliliklari.xlsx"
    try:
        df_results.to_excel(file_diff, index=False)
        print(f"\nVeri farklılıkları raporu '{file_diff}' dosyasına kaydedildi.")
    except Exception as e:
        print(f"\nRapor dosyaya yazılamadı: {e}")

