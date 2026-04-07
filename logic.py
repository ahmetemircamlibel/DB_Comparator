import sqlalchemy
from sqlalchemy import create_engine, inspect, text
import pandas as pd
import os
import re
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

def parse_ado_connection_string(conn_str):
    """
    ADO.NET formatındaki connection string'i SQLAlchemy formatına çevirir.
    
    Giriş formatı:
    User ID=user;Password=pass;Host=host;Port=5432;Database=dbname;...
    
    Çıkış formatı:
    postgresql://user:pass@host:port/dbname
    """
    # Parametreleri ayıkla
    params = {}
    for part in conn_str.split(';'):
        part = part.strip()
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.strip().lower()] = value.strip()
    
    # Gerekli alanları al
    user = params.get('user id') or params.get('userid') or params.get('user') or params.get('username')
    password = params.get('password') or params.get('pwd')
    host = params.get('host') or params.get('server') or params.get('data source')
    port = params.get('port', '5432')
    database = params.get('database') or params.get('initial catalog') or params.get('db')
    
    if not all([user, password, host, database]):
        return None
    
    # SQLAlchemy URL oluştur (PostgreSQL varsayılan)
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"

def get_db_engine(url):
    """
    Veritabanı bağlantısı oluşturur.
    Hem SQLAlchemy formatını hem de ADO.NET formatını kabul eder.
    """
    try:
        # Eğer SQLAlchemy formatı değilse (postgresql://, mysql://, sqlite:// ile başlamıyorsa)
        if not re.match(r'^(postgresql|mysql|sqlite|mssql|oracle)(\+\w+)?://', url):
            # ADO.NET formatı olarak dene
            converted_url = parse_ado_connection_string(url)
            if converted_url:
                url = converted_url
            else:
                return None
        
        # Connection pooling ile engine oluştur (performans için)
        engine = create_engine(
            url,
            pool_size=10,           # Havuzdaki bağlantı sayısı
            max_overflow=20,        # Ekstra bağlantı sayısı
            pool_timeout=30,        # Bağlantı bekleme süresi
            pool_recycle=1800,      # 30 dakikada bağlantıları yenile
            pool_pre_ping=True      # Bağlantı canlılığını kontrol et
        )
        return engine
    except Exception as e:
        print(f"DB Engine hatası: {e}")
        return None


# ========== SNAPSHOT FONKSİYONLARI ==========
SNAPSHOTS_DIR = "snapshots"

def export_db_to_snapshot(engine, db_name, table_list, progress_callback=None, overwrite=False):
    """
    Veritabanındaki tabloları JSON dosyalarına kaydeder.
    
    Args:
        engine: SQLAlchemy engine
        db_name: Veritabanı adı (klasör adı için)
        table_list: Kaydedilecek tabloların listesi
        progress_callback: İlerleme callback fonksiyonu (current, total, table_name)
        overwrite: True ise mevcut snapshot'ı sil ve yeni oluştur
    
    Returns:
        (success, snapshot_path, message)
    """
    import json
    import shutil
    from datetime import datetime
    
    try:
        # Overwrite modunda eski snapshot'ları sil
        if overwrite:
            existing_snapshots = list_snapshots(db_name=db_name)
            for snap_name, snap_path, _ in existing_snapshots:
                try:
                    shutil.rmtree(snap_path)
                except:
                    pass
        
        # Snapshot klasörü oluştur
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"{db_name}_{timestamp}"
        snapshot_path = os.path.join(SNAPSHOTS_DIR, snapshot_name)
        os.makedirs(snapshot_path, exist_ok=True)
        
        # Metadata
        metadata = {
            "db_name": db_name,
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
            "table_count": len(table_list),
            "tables": []
        }
        
        total = len(table_list)
        for i, table_info in enumerate(table_list):
            schema = table_info.get('schema')
            table_name = table_info.get('table_name')
            full_name = table_info.get('full_name', f"{schema}.{table_name}")
            
            if progress_callback:
                progress_callback(i + 1, total, full_name)
            
            try:
                # Verileri çek
                query = f'SELECT * FROM "{schema}"."{table_name}"' if schema else f'SELECT * FROM "{table_name}"'
                df = pd.read_sql(query, engine)
                
                # JSON olarak kaydet
                safe_filename = full_name.replace(".", "_").replace("/", "_")
                file_path = os.path.join(snapshot_path, f"{safe_filename}.json")
                
                # DataFrame'i JSON'a çevir (tarih formatını düzelt)
                df_json = df.to_json(orient='records', date_format='iso', force_ascii=False)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(df_json)
                
                metadata["tables"].append({
                    "schema": schema,
                    "table_name": table_name,
                    "full_name": full_name,
                    "row_count": len(df),
                    "file": f"{safe_filename}.json"
                })
                
            except Exception as e:
                metadata["tables"].append({
                    "schema": schema,
                    "table_name": table_name,
                    "full_name": full_name,
                    "error": str(e)
                })
        
        # Metadata kaydet
        with open(os.path.join(snapshot_path, "metadata.json"), 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        return True, snapshot_path, f"{total} tablo kaydedildi"
        
    except Exception as e:
        return False, None, f"Snapshot hatası: {e}"


def load_snapshot(snapshot_path):
    """
    Snapshot klasöründen verileri yükler.
    
    Args:
        snapshot_path: Snapshot klasörünün yolu
    
    Returns:
        (success, data_dict, metadata, message)
        data_dict: {full_name: DataFrame} dictionary
    """
    import json
    
    try:
        # Metadata yükle
        metadata_path = os.path.join(snapshot_path, "metadata.json")
        if not os.path.exists(metadata_path):
            return False, None, None, "metadata.json bulunamadı"
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        data_dict = {}
        for table_info in metadata.get("tables", []):
            if "error" in table_info:
                continue
            
            file_name = table_info.get("file")
            full_name = table_info.get("full_name")
            file_path = os.path.join(snapshot_path, file_name)
            
            if os.path.exists(file_path):
                df = pd.read_json(file_path, orient='records')
                data_dict[full_name] = {
                    "schema": table_info.get("schema"),
                    "table_name": table_info.get("table_name"),
                    "data": df
                }
        
        return True, data_dict, metadata, f"{len(data_dict)} tablo yüklendi"
        
    except Exception as e:
        return False, None, None, f"Snapshot yükleme hatası: {e}"


def list_snapshots(db_name=None):
    """
    Kayıtlı snapshot'ları listeler.
    
    Args:
        db_name: Filtrelemek için DB adı (opsiyonel)
    
    Returns:
        List of (snapshot_name, path, metadata)
    """
    import json
    
    snapshots = []
    if not os.path.exists(SNAPSHOTS_DIR):
        return snapshots
    
    for name in os.listdir(SNAPSHOTS_DIR):
        path = os.path.join(SNAPSHOTS_DIR, name)
        if os.path.isdir(path):
            metadata_path = os.path.join(path, "metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    if db_name is None or metadata.get("db_name") == db_name:
                        snapshots.append((name, path, metadata))
                except:
                    pass
    
    # Tarihe göre sırala (yeniden eskiye)
    snapshots.sort(key=lambda x: x[0], reverse=True)
    return snapshots


def get_latest_snapshot_for_db(db_name, max_age_hours=24):
    """
    Belirtilen DB için en son snapshot'ı döndürür.
    Eğer max_age_hours içinde bir snapshot varsa onu döndürür, yoksa None.
    
    Args:
        db_name: Veritabanı adı
        max_age_hours: Maksimum yaş (saat cinsinden)
    
    Returns:
        (snapshot_path, metadata) veya None
    """
    from datetime import datetime, timedelta
    
    snapshots = list_snapshots(db_name=db_name)
    if not snapshots:
        return None
    
    latest = snapshots[0]  # En yeni snapshot
    metadata = latest[2]
    
    try:
        created_at = metadata.get("created_at", "")
        if created_at:
            snapshot_time = datetime.fromisoformat(created_at)
            age = datetime.now() - snapshot_time
            
            if age < timedelta(hours=max_age_hours):
                return latest[1], metadata
    except:
        pass
    
    return None

def generate_insert_sql(df, schema, table_name):
    """
    Dataframe'deki veriler için INSERT scripti üretir.
    """
    if df.empty:
        return "-- Eklenecek veri yok."
    
    full_name = f"{schema}.{table_name}" if schema else table_name
    statements = []
    
    for index, row in df.iterrows():
        cols = []
        vals = []
        
        for col_name, val in row.items():
            # _merge kolonunu atla
            if col_name == '_merge': continue
            
            cols.append(f'"{col_name}"')
            
            if pd.isna(val):
                vals.append("NULL")
            elif isinstance(val, str):
                safe_val = val.replace("'", "''") # SQL Injection / Syntax koruması
                vals.append(f"'{safe_val}'")
            elif isinstance(val, (int, float)):
                vals.append(str(val))
            elif isinstance(val, pd.Timestamp):
                vals.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S.%f')}'")  # Milisaniye dahil
            else:
                vals.append(f"'{str(val)}'")
                
        cols_str = ", ".join(cols)
        vals_str = ", ".join(vals)
        stmt = f"INSERT INTO {full_name} ({cols_str}) VALUES ({vals_str});"
        statements.append(stmt)
        
    return "\n".join(statements)

def get_table_diff_data(engine1, engine2, schema, table_name, db1_name, db2_name):
    """
    Belirli bir tablo için fark verilerini ve INSERT SQL'lerini döndürür.
    """
    try:
        if schema:
            query = f"SELECT * FROM {schema}.{table_name}"
        else:
            query = f"SELECT * FROM {table_name}"
        
        df_db1 = pd.read_sql(query, engine1)
        df_db2 = pd.read_sql(query, engine2)
        
        # Anahtar kolon bul
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
        
        if not key_col:
            return None, None, "Ortak anahtar kolon bulunamadı."
        
        merged = df_db1.merge(df_db2, on=key_col, how='outer', suffixes=('_db1', '_db2'), indicator=True)
        
        only_db1 = merged[merged['_merge'] == 'left_only']
        only_db2 = merged[merged['_merge'] == 'right_only']
        
        ids_only_db1 = only_db1[key_col].tolist()
        ids_only_db2 = only_db2[key_col].tolist()
        
        data_only_db1 = df_db1[df_db1[key_col].isin(ids_only_db1)]
        data_only_db2 = df_db2[df_db2[key_col].isin(ids_only_db2)]
        
        # SQL üret
        sql_for_db2 = ""  # DB1'de olup DB2'de olmayanlar -> DB2'ye INSERT
        sql_for_db1 = ""  # DB2'de olup DB1'de olmayanlar -> DB1'e INSERT
        
        if not data_only_db1.empty:
            sql_for_db2 = f"-- {db2_name}'e Eklenecekler ({db1_name}'de olup {db2_name}'de olmayanlar):\n"
            sql_for_db2 += generate_insert_sql(data_only_db1, schema, table_name)
        
        if not data_only_db2.empty:
            sql_for_db1 = f"-- {db1_name}'e Eklenecekler ({db2_name}'de olup {db1_name}'de olmayanlar):\n"
            sql_for_db1 += generate_insert_sql(data_only_db2, schema, table_name)
        
        return sql_for_db2, sql_for_db1, None
        
    except Exception as e:
        return None, None, str(e)


def find_definition_tables(engine):
    """
    Veritabanındaki tüm şemaları ve tabloları tarar.
    """
    inspector = inspect(engine)
    candidate_tables = []
    rejected_tables = []
    
    try:
        all_schemas = inspector.get_schema_names()
        # Sistem şemalarını hariç tut
        schemas = [s for s in all_schemas if s not in ['information_schema', 'pg_catalog']]
    except Exception as e:
        schemas = [None] # Varsayılan şema

    for schema in schemas:
        try:
            table_names = inspector.get_table_names(schema=schema)
        except Exception as e:
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
                    'reason': "Kriterlere uygun"
                })

            except Exception as e:
                pass

    return candidate_tables, rejected_tables

def compare_tables(db1_engine, db2_engine, common_tables_list, db1_name, db2_name, base_db='SYMMETRIC'):
    """
    Ortak tabloları iki DB arasında karşılaştırır.
    """
    results = []

    # Base DB'ye göre hedef DB ismini belirle (Raporlama için)
    target_db_name = db2_name if base_db == 'DB1' else db1_name if base_db == 'DB2' else "Diğer"

    for item in common_tables_list:
        schema = item['schema']
        table_name = item['table_name']
        full_name = item['full_name']
        
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

            # Sütun sırasını normalize et ve string tabanlı karşılaştır
            try:
                # Her iki tablo da boşsa, eşit kabul et
                if count_db1 == 0 and count_db2 == 0:
                    is_equal = True
                else:
                    common_cols = sorted(list(set(df_db1.columns) & set(df_db2.columns)))
                    if common_cols and count_db1 > 0 and count_db2 > 0:
                        df1_norm = df_db1[common_cols].fillna('').astype(str)
                        df2_norm = df_db2[common_cols].fillna('').astype(str)
                        
                        # Her satırı string olarak karşılaştır
                        df1_str = df1_norm.apply(lambda r: '|'.join(r), axis=1).sort_values(ignore_index=True)
                        df2_str = df2_norm.apply(lambda r: '|'.join(r), axis=1).sort_values(ignore_index=True)
                        
                        is_equal = df1_str.equals(df2_str)
                    elif count_db1 == 0 and count_db2 == 0:
                        # İkisi de boş
                        is_equal = True
                    else:
                        # Biri boş, biri dolu
                        is_equal = False
            except Exception:
                is_equal = False

            if is_equal:
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
                    
                    cnt_db1 = len(only_db1)
                    cnt_db2 = len(only_db2)
                    
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
            error_str = str(e).lower()
            if 'permission denied' in error_str:
                res['Açıklama'] = "Yetki Hatası"
                res['Notlar'] = f"Şema/tablo erişim yetkisi yok: {e}"
            elif 'does not exist' in error_str or 'relation' in error_str:
                res['Açıklama'] = "Tablo Mevcut Değil"
                res['Notlar'] = f"Hedef DB'de tablo yok: {e}"
            else:
                res['Açıklama'] = "İşlem Hatası"
                res['Notlar'] = str(e)
        
        results.append(res)

    return results


def compare_tables_from_data(db1_data, db2_data, db1_name, db2_name, base_db='SYMMETRIC'):
    """
    Dosyadan yüklenen verileri karşılaştırır (snapshot'lar için).
    
    Args:
        db1_data: {full_name: {"schema": ..., "table_name": ..., "data": DataFrame}} dictionary
        db2_data: Aynı format
        db1_name: DB1 adı
        db2_name: DB2 adı
        base_db: Karşılaştırma modu
    
    Returns:
        Karşılaştırma sonuçları listesi
    """
    results = []
    
    # Ortak tabloları bul
    common_tables = set(db1_data.keys()) & set(db2_data.keys())
    
    # Hedef DB'yi belirle
    if base_db == 'DB1':
        target_db_name = db2_name
    elif base_db == 'DB2':
        target_db_name = db1_name
    else:
        target_db_name = None
    
    for full_name in sorted(common_tables):
        info1 = db1_data[full_name]
        info2 = db2_data[full_name]
        
        schema = info1.get("schema")
        table_name = info1.get("table_name")
        df_db1 = info1.get("data", pd.DataFrame())
        df_db2 = info2.get("data", pd.DataFrame())
        
        res = {
            'Şema': schema or 'default',
            'Tablo': table_name,
            'Durum': '',
            'Açıklama': '',
            'Fark (Adet)': 0,
            f'{db1_name} Satır': len(df_db1),
            f'{db2_name} Satır': len(df_db2),
            'Eksik Kayıt': 0,
            'Fazla Kayıt': 0,
            f'Sadece {db1_name}': 0,
            f'Sadece {db2_name}': 0,
            'Notlar': ''
        }
        
        try:
            # Sütun sırasını normalize et (alfabetik)
            common_cols = sorted(list(set(df_db1.columns) & set(df_db2.columns)))
            if common_cols:
                df_db1_norm = df_db1[common_cols].sort_values(by=common_cols, ignore_index=True)
                df_db2_norm = df_db2[common_cols].sort_values(by=common_cols, ignore_index=True)
            else:
                df_db1_norm = df_db1.sort_index(axis=1)
                df_db2_norm = df_db2.sort_index(axis=1)

            if df_db1_norm.equals(df_db2_norm):
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
                    
                    cnt_db1 = len(only_db1)
                    cnt_db2 = len(only_db2)
                    
                    res[f'Sadece {db1_name}'] = cnt_db1
                    res[f'Sadece {db2_name}'] = cnt_db2
                    res['Fark (Adet)'] = cnt_db1 + cnt_db2
                    
                    if base_db == 'SYMMETRIC':
                        res['Eksik Kayıt'] = cnt_db1 + cnt_db2
                        if cnt_db1 == 0 and cnt_db2 == 0:
                            res['Açıklama'] = "Satır Sayıları Eşit Ancak İçerik Farklı"
                        else:
                            parts = []
                            if cnt_db1 > 0: parts.append(f"{db2_name}'de {cnt_db1} EKSİK")
                            if cnt_db2 > 0: parts.append(f"{db1_name}'de {cnt_db2} EKSİK")
                            res['Açıklama'] = ", ".join(parts)
                    
                    elif base_db == 'DB1':
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
        
        results.append(res)
    
    return results


def compare_tables_mixed(db_engine, file_data, table_list, db_name, file_name, db_is_target=True, base_db='SYMMETRIC'):
    """
    DB ve Dosya karışık karşılaştırma yapar.
    
    Args:
        db_engine: Canlı veritabanı bağlantısı
        file_data: Dosyadan yüklenen veriler ({full_name: {schema, table_name, data}})
        table_list: Karşılaştırılacak tabloların listesi
        db_name: Veritabanı adı
        file_name: Dosya/snapshot adı
        db_is_target: True ise DB birinci konumda (target)
        base_db: Karşılaştırma modu
    
    Returns:
        Karşılaştırma sonuçları listesi
    """
    results = []
    
    for table_info in table_list:
        schema = table_info.get('schema')
        table_name = table_info.get('table_name')
        full_name = table_info.get('full_name', f"{schema}.{table_name}")
        
        name1 = db_name if db_is_target else file_name
        name2 = file_name if db_is_target else db_name
        
        res = {
            'Şema': schema or 'default',
            'Tablo': table_name,
            'Durum': '',
            'Açıklama': '',
            'Fark (Adet)': 0,
            f'{name1} Satır': 0,
            f'{name2} Satır': 0,
            'Eksik Kayıt': 0,
            'Fazla Kayıt': 0,
            f'Sadece {name1}': 0,
            f'Sadece {name2}': 0,
            'Notlar': ''
        }
        
        try:
            # DB'den veri çek
            if schema:
                query = f'SELECT * FROM "{schema}"."{table_name}"'
            else:
                query = f'SELECT * FROM "{table_name}"'
            
            df_db = pd.read_sql(query, db_engine)
            
            # Dosyadan veri al
            if full_name in file_data:
                df_file = file_data[full_name].get('data', pd.DataFrame())
            else:
                res['Durum'] = "HATA"
                res['Açıklama'] = f"Dosyada tablo bulunamadı: {full_name}"
                results.append(res)
                continue
            
            # Pozisyona göre df1, df2 ayarla
            if db_is_target:
                df1, df2 = df_db, df_file
            else:
                df1, df2 = df_file, df_db
            
            res[f'{name1} Satır'] = len(df1)
            res[f'{name2} Satır'] = len(df2)
            
            # Satır sayısı farklıysa direkt FARKLI
            if len(df1) != len(df2):
                res['Durum'] = "FARKLI"
                res['Açıklama'] = f"Satır sayısı farkı: {len(df1)} vs {len(df2)}"
                res['Fark (Adet)'] = abs(len(df1) - len(df2))
                results.append(res)
                continue
            
            # Sütun normalizasyonu ve string'e çevirme
            try:
                common_cols = sorted(list(set(df1.columns) & set(df2.columns)))
                if common_cols:
                    df1_norm = df1[common_cols].fillna('').astype(str)
                    df2_norm = df2[common_cols].fillna('').astype(str)
                    
                    # Her satırı string olarak karşılaştır
                    df1_str = df1_norm.apply(lambda r: '|'.join(r), axis=1).sort_values(ignore_index=True)
                    df2_str = df2_norm.apply(lambda r: '|'.join(r), axis=1).sort_values(ignore_index=True)
                    
                    is_equal = df1_str.equals(df2_str)
                else:
                    is_equal = False
            except:
                is_equal = False
            
            if is_equal:
                res['Durum'] = "EŞİT"
                res['Açıklama'] = "Veriler Birebir Aynı"
            else:
                res['Durum'] = "FARKLI"
                
                # Anahtar kolon bul
                common_cols = list(set(df1.columns) & set(df2.columns))
                key_col = None
                possible_keys = ['id', 'kod', 'code', 'uuid']
                for k in possible_keys:
                    for col in common_cols:
                        if col.lower() == k:
                            key_col = col
                            break
                    if key_col:
                        break
                
                if key_col and key_col in df1.columns and key_col in df2.columns:
                    try:
                        set1 = set(df1[key_col].dropna().astype(str))
                        set2 = set(df2[key_col].dropna().astype(str))
                        only_in_1 = len(set1 - set2)
                        only_in_2 = len(set2 - set1)
                        res['Fark (Adet)'] = only_in_1 + only_in_2
                        res[f'Sadece {name1}'] = only_in_1
                        res[f'Sadece {name2}'] = only_in_2
                        
                        if only_in_1 == 0 and only_in_2 == 0:
                            res['Açıklama'] = "Satır Sayıları Eşit Ancak İçerik Farklı"
                        else:
                            res['Açıklama'] = f"{name1}'de {only_in_1}, {name2}'de {only_in_2} farklı kayıt"
                    except:
                        res['Açıklama'] = f"Satır Farkı: {abs(len(df1) - len(df2))}"
                        res['Fark (Adet)'] = abs(len(df1) - len(df2))
                else:
                    # Anahtar kolon yoksa satır sayısı farkı
                    res['Açıklama'] = f"Satır sayısı farkı ({len(df1)} vs {len(df2)})"
                    res['Fark (Adet)'] = abs(len(df1) - len(df2))
        
        except Exception as e:
            res['Durum'] = "HATA"
            res['Açıklama'] = "İşlem Hatası"
            res['Notlar'] = str(e)
        
        results.append(res)
    
    return results

def load_manual_tables_from_excel(file_path, db1_map, db2_map, engine_db1, engine_db2, db1_name, db2_name):
    """
    Excel dosyasından manuel eklenen tabloları okur ve map'lere ekler.
    """
    if not os.path.exists(file_path):
        return 0, []

    added_count = 0
    logs = []
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
                    logs.append(f"  -> {db1_name}'de BULUNDU ve EKLENDİ: {full_name}")
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
                    if not exists_db1: logs.append(f"  -> {db2_name}'de BULUNDU ve EKLENDİ: {full_name}")
                    db2_map[full_name] = {
                        'schema': schema,
                        'table_name': table,
                        'full_name': full_name,
                        'reason': "Manuel Eklendi"
                    }
                    if not exists_db1: added_count += 1

    except Exception as e:
        logs.append(f"HATA: Manuel dosya okunamadı: {e}")
    
    return added_count, logs

def save_to_excel(results, db1_name, db2_name, base_db, filename="veri_farkliliklari.xlsx"):
    """
    Sonuçları Excel dosyasına kaydeder.
    """
    try:
        df_results = pd.DataFrame(results)
        
        # Kolon sırasını Base DB'ye göre düzenle
        if base_db == 'SYMMETRIC':
            cols = ['Şema', 'Tablo', 'Durum', 'Açıklama', f'{db1_name} Satır', f'{db2_name} Satır', 'Fark (Adet)', f'Sadece {db1_name}', f'Sadece {db2_name}', 'Notlar']
        else:
            cols = ['Şema', 'Tablo', 'Durum', 'Açıklama', f'{db1_name} Satır', f'{db2_name} Satır', 'Fark (Adet)', 'Eksik Kayıt', 'Fazla Kayıt', 'Notlar']

        final_cols = [c for c in cols if c in df_results.columns]
        df_results = df_results[final_cols]
        
        df_results.to_excel(filename, index=False)
        return True, f"Rapor başarıyla '{filename}' dosyasına kaydedildi."
    except Exception as e:
        return False, f"Rapor kaydedilemedi: {e}"


# ========== TABLO MİGRASYON FONKSİYONLARI ==========

def generate_drop_cascade_sql(schema, table_name):
    """
    DROP TABLE ... CASCADE scripti üretir.
    
    Args:
        schema: Şema adı
        table_name: Tablo adı
    
    Returns:
        DROP TABLE SQL scripti
    """
    if schema:
        full_name = f'"{schema}"."{table_name}"'
    else:
        full_name = f'"{table_name}"'
    
    return f"DROP TABLE IF EXISTS {full_name} CASCADE;"


def get_table_dependencies(engine, schema, table_name):
    """
    Tablonun foreign key ilişkilerini döndürür.
    
    Args:
        engine: SQLAlchemy engine
        schema: Şema adı
        table_name: Tablo adı
    
    Returns:
        dict: {
            'references': [(ref_schema, ref_table, columns)],  # Bu tablonun referans verdiği tablolar
            'referenced_by': [(src_schema, src_table, columns)]  # Bu tabloya referans veren tablolar
        }
    """
    inspector = inspect(engine)
    
    result = {
        'references': [],      # Bu tablo hangi tablolara referans veriyor
        'referenced_by': []    # Hangi tablolar bu tabloya referans veriyor
    }
    
    # Bu tablonun foreign key'leri (referans verdiği tablolar)
    try:
        fks = inspector.get_foreign_keys(table_name, schema=schema)
        for fk in fks:
            ref_schema = fk.get('referred_schema')
            ref_table = fk.get('referred_table')
            constrained_cols = fk.get('constrained_columns', [])
            referred_cols = fk.get('referred_columns', [])
            result['references'].append({
                'schema': ref_schema,
                'table': ref_table,
                'local_columns': constrained_cols,
                'foreign_columns': referred_cols
            })
    except Exception as e:
        pass
    
    # Bu tabloya referans veren tablolar (CASCADE etkisi)
    try:
        # Tüm şemaları tara
        all_schemas = inspector.get_schema_names()
        schemas_to_check = [s for s in all_schemas if s not in ['information_schema', 'pg_catalog']]
        
        for check_schema in schemas_to_check:
            try:
                tables = inspector.get_table_names(schema=check_schema)
                for other_table in tables:
                    if check_schema == schema and other_table == table_name:
                        continue
                    
                    try:
                        other_fks = inspector.get_foreign_keys(other_table, schema=check_schema)
                        for fk in other_fks:
                            ref_schema = fk.get('referred_schema')
                            ref_table = fk.get('referred_table')
                            
                            # Bu tabloya mı referans veriyor?
                            if ref_table == table_name and (ref_schema == schema or (ref_schema is None and schema is None)):
                                result['referenced_by'].append({
                                    'schema': check_schema,
                                    'table': other_table,
                                    'local_columns': fk.get('constrained_columns', []),
                                    'foreign_columns': fk.get('referred_columns', [])
                                })
                    except:
                        pass
            except:
                pass
    except Exception as e:
        pass
    
    return result


def generate_create_table_script(engine, schema, table_name):
    """
    PostgreSQL için CREATE TABLE scripti üretir.
    Kolonlar, veri tipleri, primary key, foreign keys ve indexes dahil.
    Sequence'leri de otomatik oluşturur.
    
    Args:
        engine: SQLAlchemy engine
        schema: Şema adı
        table_name: Tablo adı
    
    Returns:
        (success, create_script, error_message)
    """
    try:
        inspector = inspect(engine)
        
        if schema:
            full_name = f'"{schema}"."{table_name}"'
        else:
            full_name = f'"{table_name}"'
        
        # 1. Kolon bilgilerini al
        columns = inspector.get_columns(table_name, schema=schema)
        
        # 2. Primary Key
        pk_info = inspector.get_pk_constraint(table_name, schema=schema)
        pk_columns = pk_info.get('constrained_columns', []) if pk_info else []
        
        # 3. Foreign Keys
        fk_constraints = inspector.get_foreign_keys(table_name, schema=schema)
        
        # 4. Unique Constraints
        try:
            unique_constraints = inspector.get_unique_constraints(table_name, schema=schema)
        except:
            unique_constraints = []
        
        # 5. Indexes
        try:
            indexes = inspector.get_indexes(table_name, schema=schema)
        except:
            indexes = []
        
        # Sequence'leri tespit et
        sequence_scripts = []
        col_definitions = []
        
        for col in columns:
            col_name = col['name']
            col_type = str(col['type'])
            nullable = col.get('nullable', True)
            default = col.get('default')
            
            col_def = f'    "{col_name}" {col_type}'
            
            if not nullable:
                col_def += " NOT NULL"
            
            if default is not None:
                # nextval içeren default'ları tespit et ve sequence oluştur
                default_str = str(default)
                if 'nextval' in default_str.lower():
                    # Sequence adını çıkar: nextval('schema.seq_name'::regclass)
                    import re
                    match = re.search(r"nextval\('([^']+)'", default_str)
                    if match:
                        seq_full_name = match.group(1)
                        # Şema ve sequence adını ayır
                        if '.' in seq_full_name:
                            seq_schema, seq_name = seq_full_name.split('.', 1)
                            seq_quoted = f'"{seq_schema}"."{seq_name}"'
                        else:
                            seq_quoted = f'"{seq_full_name}"'
                        # Sequence CREATE scripti ekle
                        sequence_scripts.append(f'CREATE SEQUENCE IF NOT EXISTS {seq_quoted};')
                
                col_def += f" DEFAULT {default}"
            
            col_definitions.append(col_def)
        
        # Primary Key constraint
        if pk_columns:
            pk_cols_str = ', '.join([f'"{c}"' for c in pk_columns])
            col_definitions.append(f"    PRIMARY KEY ({pk_cols_str})")
        
        # Foreign Key constraints
        for fk in fk_constraints:
            fk_name = fk.get('name', '')
            local_cols = fk.get('constrained_columns', [])
            ref_schema = fk.get('referred_schema')
            ref_table = fk.get('referred_table')
            ref_cols = fk.get('referred_columns', [])
            
            local_cols_str = ', '.join([f'"{c}"' for c in local_cols])
            ref_cols_str = ', '.join([f'"{c}"' for c in ref_cols])
            
            if ref_schema:
                ref_full = f'"{ref_schema}"."{ref_table}"'
            else:
                ref_full = f'"{ref_table}"'
            
            fk_def = f'    CONSTRAINT "{fk_name}" FOREIGN KEY ({local_cols_str}) REFERENCES {ref_full} ({ref_cols_str})'
            col_definitions.append(fk_def)
        
        # Unique constraints
        for uc in unique_constraints:
            uc_name = uc.get('name', '')
            uc_cols = uc.get('column_names', [])
            if uc_cols:
                uc_cols_str = ', '.join([f'"{c}"' for c in uc_cols])
                col_definitions.append(f'    CONSTRAINT "{uc_name}" UNIQUE ({uc_cols_str})')
        
        # Script'i oluştur
        create_script = ""
        
        # Önce sequence'leri oluştur
        if sequence_scripts:
            # Her sequence zaten ; ile bitiyor, newline ile ayır
            create_script += "-- Sequences\n"
            create_script += "\n".join(sequence_scripts)
            create_script += "\n\n"
        
        # CREATE TABLE
        lines = []
        lines.append(f"CREATE TABLE {full_name} (")
        lines.append(',\n'.join(col_definitions))
        lines.append(");")
        
        create_script += '\n'.join(lines)
        
        # CREATE INDEX statements
        index_scripts = []
        for idx in indexes:
            idx_name = idx.get('name')
            idx_cols = idx.get('column_names', [])
            is_unique = idx.get('unique', False)
            
            if idx_cols and idx_name:
                idx_cols_str = ', '.join([f'"{c}"' for c in idx_cols])
                unique_kw = "UNIQUE " if is_unique else ""
                index_scripts.append(f'CREATE {unique_kw}INDEX "{idx_name}" ON {full_name} ({idx_cols_str});')
        
        if index_scripts:
            create_script += "\n\n-- Indexes\n" + "\n".join(index_scripts)
        
        return True, create_script, None
        
    except Exception as e:
        return False, None, str(e)


def get_table_migration_scripts(source_engine, schema, table_name, target_schema=None, skip_dependencies=False):
    """
    Tablo migrasyon için gerekli tüm scriptleri üretir.
    
    Args:
        source_engine: Kaynak veritabanı engine
        schema: Kaynak şema adı
        table_name: Tablo adı
        target_schema: Hedef şema adı (None ise kaynak şema kullanılır)
        skip_dependencies: True ise bağımlılık kontrolü atlanır (hızlı mod)
    
    Returns:
        dict: {
            'drop_script': DROP TABLE CASCADE scripti,
            'create_script': CREATE TABLE scripti,
            'dependencies': Bağımlılık bilgileri,
            'warnings': Uyarı mesajları listesi
        }
    """
    target_schema = target_schema or schema
    
    result = {
        'drop_script': '',
        'create_script': '',
        'dependencies': None,
        'warnings': []
    }
    
    # DROP script
    result['drop_script'] = generate_drop_cascade_sql(target_schema, table_name)
    
    # Dependencies (opsiyonel - toplu işlemde atlanabilir)
    if not skip_dependencies:
        result['dependencies'] = get_table_dependencies(source_engine, schema, table_name)
        
        # CASCADE uyarısı
        referenced_by = result['dependencies'].get('referenced_by', [])
        if referenced_by:
            tables_list = [f"{d['schema']}.{d['table']}" for d in referenced_by]
            result['warnings'].append(
                f"⚠️ DİKKAT: Bu tabloya {len(referenced_by)} tablo referans veriyor. "
                f"CASCADE ile silinince bu tabloların FK constraint'leri de silinecek:\n"
                f"  - " + "\n  - ".join(tables_list)
            )
    
    # CREATE script
    success, create_script, error = generate_create_table_script(source_engine, schema, table_name)
    if success:
        # Şema farklıysa replace yap
        if target_schema != schema and schema:
            old_name = f'"{schema}"."{table_name}"'
            new_name = f'"{target_schema}"."{table_name}"'
            create_script = create_script.replace(old_name, new_name)
        result['create_script'] = create_script
    else:
        result['create_script'] = f"-- HATA: CREATE script üretilemedi: {error}"
        result['warnings'].append(f"CREATE script üretilemedi: {error}")
    
    return result


def execute_migration(target_engine, drop_script, create_script, dry_run=False):
    """
    Migrasyon scriptlerini çalıştırır.
    
    Args:
        target_engine: Hedef veritabanı engine
        drop_script: DROP TABLE scripti
        create_script: CREATE TABLE scripti
        dry_run: True ise sadece script döndür, çalıştırma
    
    Returns:
        (success, message)
    """
    if dry_run:
        return True, "Dry run - scriptler çalıştırılmadı"
    
    try:
        with target_engine.begin() as conn:
            # Önce DROP
            if drop_script:
                print(f"[EXECUTE] DROP: {drop_script}")
                conn.execute(text(drop_script))
            
            # Sonra CREATE
            if create_script:
                # CREATE scripti birden fazla statement içerebilir (sequences, indexes vs)
                # Önce yorum satırlarını kaldır
                lines = create_script.split('\n')
                clean_lines = [l for l in lines if not l.strip().startswith('--')]
                clean_script = '\n'.join(clean_lines)
                
                # Sonra ; ile böl
                statements = [s.strip() for s in clean_script.split(';') if s.strip()]
                
                for stmt in statements:
                    if stmt:
                        print(f"[EXECUTE] Statement: {stmt[:80]}...")
                        conn.execute(text(stmt))
        
        return True, "Migrasyon başarılı"
    except Exception as e:
        return False, f"Migrasyon hatası: {str(e)}"

