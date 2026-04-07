import customtkinter as ctk
import threading
import os
import sys
import subprocess
import json
from tkinter import messagebox, ttk
import logic

# Kayıtlı bağlantılar dosyası
SAVED_CONNECTIONS_FILE = "saved_connections.json"

# Tema Ayarları
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Yumuşak Renk Paleti
COLORS = {
    "bg_primary": "#2d3436",
    "bg_secondary": "#353b48",
    "bg_card": "#3d4451",
    "accent": "#74b9ff",
    "accent_hover": "#81d4fa",
    "success": "#81c784",
    "warning": "#ffb74d",
    "error": "#e57373",
    "text_primary": "#dfe6e9",
    "text_secondary": "#b2bec3",
    "text_muted": "#636e72",
    "border": "#4a5568",
    "input_bg": "#2d3436"
}


class SQLPopup(ctk.CTkToplevel):
    """SQL kodunu gösteren popup pencere"""
    def __init__(self, parent, title, sql_db2, sql_db1, db1_name, db2_name, engine1=None, engine2=None):
        super().__init__(parent)
        
        self.title(f"SQL Komutları - {title}")
        self.geometry("950x600")
        self.configure(fg_color=COLORS["bg_primary"])
        self.grab_set()
        
        self.engine1 = engine1
        self.engine2 = engine2
        
        header = ctk.CTkLabel(self, text=f"{title}", font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text_primary"])
        header.pack(pady=(20, 5))
        
        header_sub = ctk.CTkLabel(self, text="INSERT Komutları", font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"])
        header_sub.pack(pady=(0, 15))
        
        self.tabview = ctk.CTkTabview(self, width=900, height=420, fg_color=COLORS["bg_secondary"],
            segmented_button_fg_color=COLORS["bg_card"], segmented_button_selected_color=COLORS["accent"],
            segmented_button_unselected_color=COLORS["bg_card"])
        self.tabview.pack(padx=20, pady=10, fill="both", expand=True)
        
        tab1_name = f"{db2_name}'e Ekle"
        self.tabview.add(tab1_name)
        self.txt_db2 = ctk.CTkTextbox(self.tabview.tab(tab1_name), font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLORS["bg_primary"], text_color=COLORS["text_primary"])
        self.txt_db2.pack(padx=10, pady=10, fill="both", expand=True)
        self.txt_db2.insert("0.0", sql_db2 if sql_db2 else "-- Bu veritabanına eklenecek kayıt yok.")
        
        tab2_name = f"{db1_name}'e Ekle"
        self.tabview.add(tab2_name)
        self.txt_db1 = ctk.CTkTextbox(self.tabview.tab(tab2_name), font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLORS["bg_primary"], text_color=COLORS["text_primary"])
        self.txt_db1.pack(padx=10, pady=10, fill="both", expand=True)
        self.txt_db1.insert("0.0", sql_db1 if sql_db1 else "-- Bu veritabanına eklenecek kayıt yok.")
        
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=15)
        
        # Aktarma butonu (DB'ye yazma)
        self.btn_execute = ctk.CTkButton(self.btn_frame, text="DB'ye Aktar", command=self.execute_sql,
            fg_color=COLORS["success"], hover_color="#66bb6a", text_color="white",
            height=36, width=130, font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_execute.pack(side="left", padx=8)
        
        self.btn_copy = ctk.CTkButton(self.btn_frame, text="Kopyala", command=self.copy_active_tab,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"],
            height=36, width=120, font=ctk.CTkFont(size=13))
        self.btn_copy.pack(side="left", padx=8)
        
        self.btn_close = ctk.CTkButton(self.btn_frame, text="Kapat", command=self.destroy,
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"], height=36, width=100, font=ctk.CTkFont(size=13))
        self.btn_close.pack(side="left", padx=8)
        
        self.sql_db2 = sql_db2
        self.sql_db1 = sql_db1
        self.tab1_name = tab1_name
        self.tab2_name = tab2_name
        self.db1_name = db1_name
        self.db2_name = db2_name
        
    def copy_active_tab(self):
        current_tab = self.tabview.get()
        text = self.sql_db2 if self.tab1_name in current_tab else self.sql_db1
        text = text if text else ""
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Başarılı", "SQL komutları panoya kopyalandı.")

    def execute_sql(self):
        """Aktif sekmedeki SQL komutlarını ilgili DB'de çalıştır"""
        current_tab = self.tabview.get()
        
        if self.tab1_name in current_tab:
            # DB2'ye ekle
            sql = self.sql_db2
            target_engine = self.engine2
            target_name = self.db2_name
        else:
            # DB1'e ekle
            sql = self.sql_db1
            target_engine = self.engine1
            target_name = self.db1_name
        
        if not sql:
            messagebox.showinfo("Bilgi", "Aktarılacak SQL komutu yok.")
            return
        
        # Sadece INSERT satırlarını al (yorum satırlarını atla)
        sql_lines = [l.strip() for l in sql.split('\n') if l.strip() and not l.strip().startswith('--')]
        insert_lines = [l for l in sql_lines if l.upper().startswith('INSERT')]
        
        if not insert_lines:
            messagebox.showinfo("Bilgi", "Aktarılacak INSERT komutu yok.")
            return
        
        if not target_engine:
            messagebox.showerror("Hata", f"{target_name} veritabanı bağlantısı yok.\n(Dosya modunda çalışıyorsanız aktarma yapılamaz)")
            return
        
        # INSERT sayısını göster
        count = len(insert_lines)
        
        # Onay iste
        confirm = messagebox.askyesno(
            "Onay",
            f"{target_name} veritabanına {count} adet INSERT komutu çalıştırılacak.\n\n"
            f"⚠️ DİKKAT: Bu işlem geri alınamaz!\n\n"
            f"Devam etmek istiyor musunuz?",
            icon="warning"
        )
        
        if not confirm:
            return
        
        try:
            self.btn_execute.configure(state="disabled", text="Aktarılıyor...")
            self.update()
            
            success_count = 0
            error_count = 0
            errors = []
            
            with target_engine.connect() as conn:
                for line in insert_lines:
                    try:
                        conn.execute(logic.text(line))
                        success_count += 1
                    except Exception as e:
                        error_count += 1
                        errors.append(str(e)[:100])
                conn.commit()
            
            if error_count == 0:
                messagebox.showinfo("Başarılı", f"{success_count} adet kayıt {target_name} veritabanına eklendi.")
                self.btn_execute.configure(text="✓ Tamamlandı", fg_color=COLORS["success"])
            else:
                messagebox.showwarning("Kısmi Başarı", 
                    f"Başarılı: {success_count}, Hatalı: {error_count}\n\n"
                    f"İlk hata: {errors[0] if errors else 'Bilinmiyor'}")
                self.btn_execute.configure(text=f"✓ {success_count} Eklendi", fg_color=COLORS["warning"])
                
        except Exception as e:
            messagebox.showerror("Hata", f"Aktarım başarısız:\n{str(e)[:200]}")
            self.btn_execute.configure(state="normal", text="DB'ye Aktar")


class AddTableDialog(ctk.CTkToplevel):
    """Manuel tablo ekleme dialogu"""
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("Manuel Tablo Ekle")
        self.geometry("450x280")
        self.configure(fg_color=COLORS["bg_secondary"])
        self.result = None
        
        # İçeriği oluşturmadan önce pencereyi göster
        self.update()
        
        # Ana frame
        main_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"])
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Başlık
        ctk.CTkLabel(main_frame, text="Karşılaştırmaya Tablo Ekle", 
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text_primary"]).pack(pady=(0, 20))
        
        # Şema
        schema_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        schema_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(schema_frame, text="Şema:", width=80, anchor="w",
            font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"]).pack(side="left")
        self.schema_entry = ctk.CTkEntry(schema_frame, placeholder_text="örn: tanimlama, public", 
            height=36, fg_color=COLORS["bg_card"], border_color=COLORS["border"], text_color=COLORS["text_primary"])
        self.schema_entry.pack(side="left", fill="x", expand=True)
        
        # Tablo
        table_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        table_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(table_frame, text="Tablo:", width=80, anchor="w",
            font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"]).pack(side="left")
        self.table_entry = ctk.CTkEntry(table_frame, placeholder_text="örn: users, products", 
            height=36, fg_color=COLORS["bg_card"], border_color=COLORS["border"], text_color=COLORS["text_primary"])
        self.table_entry.pack(side="left", fill="x", expand=True)
        
        # Butonlar
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(pady=(25, 0))
        
        ctk.CTkButton(btn_frame, text="Ekle", command=self.on_add, fg_color=COLORS["success"],
            hover_color="#66bb6a", text_color="white", width=120, height=38,
            font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="İptal", command=self.on_cancel, fg_color=COLORS["bg_card"],
            hover_color=COLORS["border"], text_color=COLORS["text_primary"], width=100, height=38).pack(side="left", padx=8)
        
        # Modal yap (after ile)
        self.after(100, lambda: self.grab_set())
        self.after(100, lambda: self.schema_entry.focus())
    
    def on_cancel(self):
        self.result = None
        self.destroy()
    
    def on_add(self):
        schema = self.schema_entry.get().strip()
        table = self.table_entry.get().strip()
        if table:
            self.result = {"schema": schema or "public", "table_name": table, 
                          "full_name": f"{schema}.{table}" if schema else table, "reason": "Manuel Eklendi"}
            self.destroy()
        else:
            messagebox.showwarning("Uyarı", "Tablo adı gereklidir.")


class TableMigrationDialog(ctk.CTkToplevel):
    """Tablo yapısı migrasyon popup penceresi - DROP CASCADE ve CREATE TABLE"""
    def __init__(self, parent, schema, table_name, source_engine, target_engine, source_name, target_name):
        super().__init__(parent)
        
        self.schema = schema
        self.table_name = table_name
        self.source_engine = source_engine
        self.target_engine = target_engine
        self.source_name = source_name
        self.target_name = target_name
        
        full_name = f"{schema}.{table_name}" if schema else table_name
        self.title(f"Tablo Yapısı Aktarımı - {full_name}")
        self.geometry("1000x700")
        self.configure(fg_color=COLORS["bg_primary"])
        
        # Pencere görünür olduktan sonra grab_set yap
        self.after(100, self._delayed_grab)
        
        # Header
        header_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=0)
        header_frame.pack(fill="x", padx=0, pady=0)
        
        ctk.CTkLabel(header_frame, text=f"📦 {full_name}", 
            font=ctk.CTkFont(size=18, weight="bold"), 
            text_color=COLORS["text_primary"]).pack(side="left", padx=20, pady=15)
        
        ctk.CTkLabel(header_frame, text=f"{source_name} → {target_name}", 
            font=ctk.CTkFont(size=12), 
            text_color=COLORS["text_secondary"]).pack(side="left", padx=10, pady=15)
        
        # Uyarı alanı
        self.warning_frame = ctk.CTkFrame(self, fg_color=COLORS["warning"], corner_radius=8)
        self.warning_label = ctk.CTkLabel(self.warning_frame, text="", 
            font=ctk.CTkFont(size=11), text_color=COLORS["bg_primary"], 
            wraplength=950, justify="left")
        self.warning_label.pack(padx=15, pady=10)
        
        # Tab view
        self.tabview = ctk.CTkTabview(self, width=960, height=450, 
            fg_color=COLORS["bg_secondary"],
            segmented_button_fg_color=COLORS["bg_card"], 
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_unselected_color=COLORS["bg_card"])
        self.tabview.pack(padx=20, pady=10, fill="both", expand=True)
        
        # DROP Tab
        self.tabview.add("DROP CASCADE")
        self.txt_drop = ctk.CTkTextbox(self.tabview.tab("DROP CASCADE"), 
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLORS["bg_primary"], text_color=COLORS["text_primary"])
        self.txt_drop.pack(padx=10, pady=10, fill="both", expand=True)
        
        # CREATE Tab
        self.tabview.add("CREATE TABLE")
        self.txt_create = ctk.CTkTextbox(self.tabview.tab("CREATE TABLE"), 
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLORS["bg_primary"], text_color=COLORS["text_primary"])
        self.txt_create.pack(padx=10, pady=10, fill="both", expand=True)
        
        # Dependencies Tab
        self.tabview.add("Bağımlılıklar")
        self.txt_deps = ctk.CTkTextbox(self.tabview.tab("Bağımlılıklar"), 
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLORS["bg_primary"], text_color=COLORS["text_primary"])
        self.txt_deps.pack(padx=10, pady=10, fill="both", expand=True)
        
        # Button frame
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=15)
        
        self.btn_execute = ctk.CTkButton(self.btn_frame, text="🚀 DROP + CREATE", 
            command=self.execute_migration,
            fg_color=COLORS["success"], hover_color="#66bb6a", text_color="white",
            height=40, width=150, font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_execute.pack(side="left", padx=8)
        
        # Sadece DROP CASCADE çalıştır butonu
        self.btn_drop_only = ctk.CTkButton(self.btn_frame, text="🗑️ Sadece DROP", 
            command=self.execute_drop_only,
            fg_color=COLORS["error"], hover_color="#ef5350", text_color="white",
            height=40, width=130, font=ctk.CTkFont(size=13, weight="bold"))
        self.btn_drop_only.pack(side="left", padx=8)
        
        self.btn_copy_drop = ctk.CTkButton(self.btn_frame, text="DROP Kopyala", 
            command=lambda: self.copy_text(self.txt_drop),
            fg_color=COLORS["warning"], hover_color="#ffa726", text_color=COLORS["bg_primary"],
            height=40, width=120, font=ctk.CTkFont(size=12))
        self.btn_copy_drop.pack(side="left", padx=8)
        
        self.btn_copy_create = ctk.CTkButton(self.btn_frame, text="CREATE Kopyala", 
            command=lambda: self.copy_text(self.txt_create),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"],
            height=40, width=120, font=ctk.CTkFont(size=12))
        self.btn_copy_create.pack(side="left", padx=8)
        
        self.btn_close = ctk.CTkButton(self.btn_frame, text="Kapat", command=self.destroy,
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"], 
            height=40, width=80, font=ctk.CTkFont(size=12))
        self.btn_close.pack(side="left", padx=8)
        
        # Scriptleri yükle
        self.scripts = None
        self.load_migration_scripts()
    
    def _delayed_grab(self):
        """Pencere görünür olduktan sonra grab_set yap"""
        try:
            self.grab_set()
        except Exception:
            pass  # Hata olursa sessizce devam et
    
    def load_migration_scripts(self):
        """Migrasyon scriptlerini yükle"""
        try:
            self.scripts = logic.get_table_migration_scripts(
                self.source_engine, self.schema, self.table_name
            )
            
            # DROP script
            self.txt_drop.delete("0.0", "end")
            self.txt_drop.insert("0.0", f"-- {self.target_name} veritabanında çalıştırılacak:\n\n")
            self.txt_drop.insert("end", self.scripts['drop_script'])
            
            # CREATE script
            self.txt_create.delete("0.0", "end")
            self.txt_create.insert("0.0", f"-- {self.source_name} yapısından kopyalanarak {self.target_name}'de oluşturulacak:\n\n")
            self.txt_create.insert("end", self.scripts['create_script'])
            
            # Dependencies
            deps = self.scripts.get('dependencies', {})
            deps_text = "=== TABLO BAĞIMLILIKLARI ===\n\n"
            
            refs = deps.get('references', [])
            if refs:
                deps_text += f"📤 Bu tablo referans veriyor ({len(refs)} tablo):\n"
                for r in refs:
                    deps_text += f"   → {r['schema']}.{r['table']} ({', '.join(r['local_columns'])} → {', '.join(r['foreign_columns'])})\n"
                deps_text += "\n"
            else:
                deps_text += "📤 Bu tablo hiçbir tabloya referans vermiyor.\n\n"
            
            ref_by = deps.get('referenced_by', [])
            if ref_by:
                deps_text += f"📥 Bu tabloya referans veriyor ({len(ref_by)} tablo):\n"
                for r in ref_by:
                    deps_text += f"   ← {r['schema']}.{r['table']} ({', '.join(r['local_columns'])} → {', '.join(r['foreign_columns'])})\n"
                deps_text += "\n⚠️ CASCADE ile silindiğinde bu tabloların FK constraint'leri de silinecek!\n"
            else:
                deps_text += "📥 Hiçbir tablo bu tabloya referans vermiyor.\n"
            
            self.txt_deps.delete("0.0", "end")
            self.txt_deps.insert("0.0", deps_text)
            
            # Uyarıları göster
            warnings = self.scripts.get('warnings', [])
            if warnings:
                self.warning_frame.pack(fill="x", padx=20, pady=(10, 0))
                self.warning_label.configure(text="\n".join(warnings))
            else:
                self.warning_frame.pack_forget()
                
        except Exception as e:
            import traceback
            error_msg = f"HATA: Script yüklenemedi!\n\n{str(e)}\n\n{traceback.format_exc()}"
            print(f"[TableMigrationDialog] {error_msg}")  # Terminal'e yaz
            
            # Tüm sekmelere hata mesajı yaz
            self.txt_drop.delete("0.0", "end")
            self.txt_drop.insert("0.0", f"-- {error_msg}")
            
            self.txt_create.delete("0.0", "end") 
            self.txt_create.insert("0.0", f"-- {error_msg}")
            
            self.txt_deps.delete("0.0", "end")
            self.txt_deps.insert("0.0", error_msg)
            
            # Uyarı göster
            self.warning_frame.pack(fill="x", padx=20, pady=(10, 0))
            self.warning_label.configure(text=f"⚠️ Script yükleme hatası: {str(e)[:100]}")
    
    def copy_text(self, textbox):
        """Textbox içeriğini panoya kopyala"""
        text = textbox.get("0.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Kopyalandı", "SQL scripti panoya kopyalandı.")
    
    def execute_migration(self):
        """Migrasyon scriptlerini hedef DB'de çalıştır"""
        if not self.scripts:
            messagebox.showerror("Hata", "Scriptler yüklenmedi.")
            return
        
        if not self.target_engine:
            messagebox.showerror("Hata", f"{self.target_name} veritabanı bağlantısı yok.")
            return
        
        full_name = f"{self.schema}.{self.table_name}" if self.schema else self.table_name
        
        # Onay iste
        confirm = messagebox.askyesno(
            "⚠️ DİKKAT - GERİ ALINAMAZ İŞLEM",
            f"Bu işlem {self.target_name} veritabanında şunları yapacak:\n\n"
            f"1. DROP TABLE {full_name} CASCADE\n"
            f"   → Tablo ve tüm bağımlı FK'lar silinecek!\n\n"
            f"2. CREATE TABLE {full_name}\n"
            f"   → {self.source_name}'daki yapı ile yeniden oluşturulacak\n\n"
            f"⚠️ VERİLER KAYBOLACAK! Bu işlem geri alınamaz!\n\n"
            f"Devam etmek istiyor musunuz?",
            icon="warning"
        )
        
        if not confirm:
            return
        
        # İkinci onay
        confirm2 = messagebox.askyesno(
            "Son Onay",
            f"'{full_name}' tablosu {self.target_name}'de silinip yeniden oluşturulacak.\n\n"
            "EMINSENIZ 'Yes' butonuna tıklayın.",
            icon="warning"
        )
        
        if not confirm2:
            return
        
        try:
            self.btn_execute.configure(state="disabled", text="İşleniyor...")
            self.update()
            
            success, message = logic.execute_migration(
                self.target_engine,
                self.scripts['drop_script'],
                self.scripts['create_script']
            )
            
            if success:
                messagebox.showinfo("Başarılı", f"✓ Tablo başarıyla aktarıldı!\n\n{message}")
                self.btn_execute.configure(text="✓ Tamamlandı", fg_color=COLORS["success"])
            else:
                messagebox.showerror("Hata", f"Migrasyon başarısız:\n{message}")
                self.btn_execute.configure(state="normal", text="🚀 DROP + CREATE")
                
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmeyen hata:\n{str(e)}")
            self.btn_execute.configure(state="normal", text="🚀 DROP + CREATE")

    def execute_drop_only(self):
        """Sadece DROP CASCADE scriptini hedef DB'de çalıştır"""
        if not self.scripts:
            messagebox.showerror("Hata", "Scriptler yüklenmedi.")
            return
        
        if not self.target_engine:
            messagebox.showerror("Hata", f"{self.target_name} veritabanı bağlantısı yok.")
            return
        
        full_name = f"{self.schema}.{self.table_name}" if self.schema else self.table_name
        
        # Onay iste
        confirm = messagebox.askyesno(
            "⚠️ TABLO SİLİNECEK!",
            f"Bu işlem {self.target_name} veritabanında şunu yapacak:\n\n"
            f"DROP TABLE {full_name} CASCADE\n\n"
            f"⚠️ TABLO VE TÜM VERİLERİ SİLİNECEK!\n"
            f"⚠️ Bu tabloya referans veren FK'lar da silinecek!\n\n"
            f"Bu işlem GERİ ALINAMAZ!\n\n"
            f"Devam etmek istiyor musunuz?",
            icon="warning"
        )
        
        if not confirm:
            return
        
        try:
            self.btn_drop_only.configure(state="disabled", text="Siliniyor...")
            self.update()
            
            # Sadece DROP çalıştır (CREATE yok)
            success, message = logic.execute_migration(
                self.target_engine,
                self.scripts['drop_script'],
                None  # CREATE script yok
            )
            
            if success:
                messagebox.showinfo("Başarılı", f"✓ Tablo silindi!\n\nDROP TABLE {full_name} CASCADE başarılı.")
                self.btn_drop_only.configure(text="✓ Silindi", fg_color=COLORS["text_muted"])
            else:
                messagebox.showerror("Hata", f"Silme işlemi başarısız:\n{message}")
                self.btn_drop_only.configure(state="normal", text="🗑️ Sadece DROP")
                
        except Exception as e:
            messagebox.showerror("Hata", f"Beklenmeyen hata:\n{str(e)}")
            self.btn_drop_only.configure(state="normal", text="🗑️ Sadece DROP")


class BulkDataTransferDialog(ctk.CTkToplevel):
    """Toplu paralel veri aktarım popup penceresi"""
    def __init__(self, parent, tables, source_engine, target_engine, source_name, target_name):
        super().__init__(parent)
        
        self.tables = tables
        self.source_engine = source_engine
        self.target_engine = target_engine
        self.source_name = source_name
        self.target_name = target_name
        
        self.title(f"Toplu Veri Aktarımı - {len(tables)} Tablo")
        self.geometry("700x500")
        self.configure(fg_color=COLORS["bg_primary"])
        
        self.after(100, self._delayed_grab)
        
        # Header
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=0)
        header.pack(fill="x")
        
        ctk.CTkLabel(header, text=f"📤 Toplu Veri Aktarımı - {len(tables)} Tablo", 
            font=ctk.CTkFont(size=16, weight="bold"), 
            text_color=COLORS["text_primary"]).pack(side="left", padx=20, pady=12)
        
        ctk.CTkLabel(header, text=f"{source_name} → {target_name}", 
            font=ctk.CTkFont(size=12), 
            text_color=COLORS["text_muted"]).pack(side="right", padx=20, pady=12)
        
        # Log text alanı
        self.log_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=8)
        self.log_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        self.log_text = ctk.CTkTextbox(self.log_frame, height=300, 
            fg_color=COLORS["bg_card"], text_color=COLORS["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Progress frame
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=20, pady=5)
        
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="Hazırlanıyor...", 
            font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"])
        self.progress_label.pack(side="left")
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=250)
        self.progress_bar.pack(side="right", padx=10)
        self.progress_bar.set(0)
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        self.btn_start = ctk.CTkButton(btn_frame, text="🚀 Aktarımı Başlat", 
            command=self.start_transfer,
            fg_color=COLORS["success"], hover_color="#66bb6a", text_color="white",
            height=40, width=150, font=ctk.CTkFont(size=12, weight="bold"))
        self.btn_start.pack(side="left", padx=8)
        
        self.btn_close = ctk.CTkButton(btn_frame, text="Kapat", command=self.destroy,
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"], 
            height=40, width=80, font=ctk.CTkFont(size=12))
        self.btn_close.pack(side="left", padx=8)
        
        self.log_text.insert("end", f"Toplam {len(tables)} tablo aktarılacak.\n")
        self.log_text.insert("end", f"Kaynak: {source_name}\n")
        self.log_text.insert("end", f"Hedef: {target_name}\n")
        self.log_text.insert("end", "=" * 50 + "\n\n")
        self.log_text.insert("end", "Aktarımı başlatmak için butona tıklayın.\n")
    
    def _delayed_grab(self):
        try:
            self.grab_set()
        except:
            pass
    
    def start_transfer(self):
        """Paralel veri aktarımını başlat"""
        import threading
        
        self.btn_start.configure(state="disabled", text="Aktarılıyor...")
        self.log_text.delete("0.0", "end")
        self.log_text.insert("end", "Paralel veri aktarımı başlatılıyor...\n\n")
        
        self._completed = 0
        self._success = 0
        self._errors = []
        self._total_rows = 0
        self._done = False
        
        def transfer_single(table):
            """Tek tablo için veri aktarımı"""
            import pandas as pd
            schema = table['schema']
            table_name = table['table_name']
            full_name = f"{schema}.{table_name}" if schema else table_name
            
            try:
                if schema:
                    query = f'SELECT * FROM "{schema}"."{table_name}"'
                else:
                    query = f'SELECT * FROM "{table_name}"'
                
                df = pd.read_sql(query, self.source_engine)
                row_count = len(df)
                
                if row_count > 0:
                    df.to_sql(
                        table_name, 
                        self.target_engine, 
                        schema=schema,
                        if_exists='append',
                        index=False,
                        method='multi',
                        chunksize=1000
                    )
                
                return full_name, row_count, None
            except Exception as e:
                return full_name, 0, str(e)
        
        def background_transfer():
            """Arka planda paralel aktarım"""
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(transfer_single, table): table 
                           for table in self.tables}
                
                for future in as_completed(futures):
                    full_name, row_count, error = future.result()
                    self._completed += 1
                    
                    if error:
                        self._errors.append({'table': full_name, 'error': error})
                    else:
                        self._success += 1
                        self._total_rows += row_count
            
            self._done = True
        
        def update_ui():
            """UI güncelle"""
            if not self._done:
                self.progress_label.configure(text=f"Aktarılıyor... ({self._completed}/{len(self.tables)})")
                self.progress_bar.set(self._completed / len(self.tables) if len(self.tables) > 0 else 0)
                self.after(200, update_ui)
            else:
                # Tamamlandı
                self.progress_label.configure(text=f"✓ Tamamlandı: {self._success} tablo, {self._total_rows} satır")
                self.progress_bar.set(1.0)
                
                self.log_text.insert("end", f"\n{'=' * 50}\n")
                self.log_text.insert("end", f"✓ Başarılı: {self._success} tablo\n")
                self.log_text.insert("end", f"✓ Toplam Satır: {self._total_rows}\n")
                
                if self._errors:
                    self.log_text.insert("end", f"\n❌ Hatalı: {len(self._errors)} tablo\n")
                    for err in self._errors:
                        self.log_text.insert("end", f"  • {err['table']}: {err['error'][:60]}...\n")
                
                # Log dosyasına yaz
                from datetime import datetime
                log_file = f"bulk_transfer_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                try:
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write(self.log_text.get("0.0", "end"))
                    self.log_text.insert("end", f"\n📄 Log: {log_file}\n")
                except:
                    pass
                
                self.btn_start.configure(text="✓ Tamamlandı", fg_color=COLORS["success"] if not self._errors else COLORS["warning"])
        
        # Thread başlat
        thread = threading.Thread(target=background_transfer, daemon=True)
        thread.start()
        self.after(200, update_ui)


class BulkMigrationDialog(ctk.CTkToplevel):
    """Toplu tablo migrasyon popup penceresi"""
    def __init__(self, parent, tables, source_engine, target_engine, source_name, target_name):
        super().__init__(parent)
        
        self.tables = tables
        self.source_engine = source_engine
        self.target_engine = target_engine
        self.source_name = source_name
        self.target_name = target_name
        
        self.title(f"Toplu İşlem - {len(tables)} Tablo")
        self.geometry("1100x750")
        self.configure(fg_color=COLORS["bg_primary"])
        self.after(100, self._delayed_grab)
        
        # Header
        header_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=0)
        header_frame.pack(fill="x", padx=0, pady=0)
        
        ctk.CTkLabel(header_frame, text=f"⚡ Toplu İşlem - {len(tables)} Tablo", 
            font=ctk.CTkFont(size=18, weight="bold"), 
            text_color=COLORS["text_primary"]).pack(side="left", padx=20, pady=15)
        
        ctk.CTkLabel(header_frame, text=f"{source_name} → {target_name}", 
            font=ctk.CTkFont(size=12), 
            text_color=COLORS["text_secondary"]).pack(side="left", padx=10, pady=15)
        
        # Uyarı
        warning_frame = ctk.CTkFrame(self, fg_color=COLORS["error"], corner_radius=8)
        warning_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(warning_frame, 
            text="⚠️ DİKKAT: Bu işlem seçili tüm tabloları hedef veritabanında silip yeniden oluşturacak! VERİLER KAYBOLACAK!",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="white",
            wraplength=1050).pack(padx=15, pady=10)
        
        # Script alanı
        self.txt_scripts = ctk.CTkTextbox(self, 
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLORS["bg_secondary"], text_color=COLORS["text_primary"])
        self.txt_scripts.pack(padx=20, pady=10, fill="both", expand=True)
        
        # Progress
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=20, pady=5)
        
        self.progress_label = ctk.CTkLabel(self.progress_frame, text="Scriptler hazırlanıyor...",
            font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"])
        self.progress_label.pack(side="left")
        
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=300)
        self.progress_bar.pack(side="right", padx=10)
        self.progress_bar.set(0)
        
        # Button frame
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=15)
        
        self.btn_execute_all = ctk.CTkButton(self.btn_frame, text="🚀 DROP+CREATE", 
            command=self.execute_all,
            fg_color=COLORS["success"], hover_color="#66bb6a", text_color="white",
            height=40, width=150, font=ctk.CTkFont(size=12, weight="bold"), state="disabled")
        self.btn_execute_all.pack(side="left", padx=5)
        
        self.btn_transfer_data = ctk.CTkButton(self.btn_frame, text="📤 Veri Aktar", 
            command=self.transfer_all_data,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"],
            height=40, width=110, font=ctk.CTkFont(size=11, weight="bold"), state="disabled")
        self.btn_transfer_data.pack(side="left", padx=4)
        
        self.btn_create_only = ctk.CTkButton(self.btn_frame, text="➕ Sadece CREATE", 
            command=self.create_only,
            fg_color="#4CAF50", hover_color="#66bb6a", text_color="white",
            height=40, width=125, font=ctk.CTkFont(size=11, weight="bold"), state="disabled")
        self.btn_create_only.pack(side="left", padx=4)
        
        self.btn_drop_all = ctk.CTkButton(self.btn_frame, text="🗑️ Sadece DROP", 
            command=self.drop_all,
            fg_color=COLORS["error"], hover_color="#ef5350", text_color="white",
            height=40, width=120, font=ctk.CTkFont(size=11, weight="bold"), state="disabled")
        self.btn_drop_all.pack(side="left", padx=4)
        
        self.btn_copy = ctk.CTkButton(self.btn_frame, text="Kopyala", 
            command=self.copy_scripts,
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"], text_color=COLORS["text_primary"],
            height=40, width=80, font=ctk.CTkFont(size=12))
        self.btn_copy.pack(side="left", padx=5)
        
        self.btn_close = ctk.CTkButton(self.btn_frame, text="Kapat", command=self.destroy,
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"], 
            height=40, width=80, font=ctk.CTkFont(size=12))
        self.btn_close.pack(side="left", padx=5)
        
        # Scriptleri arka planda yükle
        self.all_scripts = []
        self.after(200, self.generate_scripts)
    
    def _delayed_grab(self):
        try:
            self.grab_set()
        except:
            pass
    
    def generate_scripts(self):
        """Tüm tablolar için scriptleri arka planda paralel üret"""
        import threading
        
        self.txt_scripts.delete("0.0", "end")
        self.txt_scripts.insert("0.0", f"-- {self.target_name} veritabanında çalıştırılacak scriptler\n")
        self.txt_scripts.insert("end", f"-- Kaynak: {self.source_name}\n")
        self.txt_scripts.insert("end", f"-- Toplam: {len(self.tables)} tablo\n")
        self.txt_scripts.insert("end", "=" * 60 + "\n\n")
        
        total = len(self.tables)
        self.all_scripts = []
        self._results = {}
        self._errors = {}
        self._completed = 0
        self._total = total
        self._generation_done = False
        
        def generate_single(index, table):
            """Tek tablo için script üret"""
            schema = table['schema']
            table_name = table['table_name']
            full_name = f"{schema}.{table_name}" if schema else table_name
            
            try:
                # skip_dependencies=True ile hızlı mod
                scripts = logic.get_table_migration_scripts(
                    self.source_engine, schema, table_name, skip_dependencies=True
                )
                return index, {
                    'schema': schema,
                    'table_name': table_name,
                    'full_name': full_name,
                    'drop_script': scripts['drop_script'],
                    'create_script': scripts['create_script']
                }, None
            except Exception as e:
                return index, None, str(e)
        
        def background_generate():
            """Arka planda tüm scriptleri üret"""
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            # 20 paralel worker (hızlı üretim için)
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(generate_single, i, table): i 
                           for i, table in enumerate(self.tables)}
                
                for future in as_completed(futures):
                    idx, result, error = future.result()
                    if result:
                        self._results[idx] = result
                    else:
                        self._errors[idx] = error
                    self._completed += 1
            
            self._generation_done = True
        
        def update_ui():
            """UI'ı güncelle (main thread'de)"""
            if not self._generation_done:
                self.progress_label.configure(text=f"Üretiliyor... ({self._completed}/{self._total})")
                self.progress_bar.set(self._completed / self._total if self._total > 0 else 0)
                self.after(200, update_ui)
            else:
                # Tamamlandı, sonuçları yaz
                for i in range(self._total):
                    if i in self._results:
                        r = self._results[i]
                        self.all_scripts.append(r)
                        self.txt_scripts.insert("end", f"-- [{i+1}] {r['full_name']}\n")
                        self.txt_scripts.insert("end", r['drop_script'] + "\n")
                        self.txt_scripts.insert("end", r['create_script'] + "\n\n")
                    elif i in self._errors:
                        table = self.tables[i]
                        full_name = f"{table['schema']}.{table['table_name']}" if table['schema'] else table['table_name']
                        self.txt_scripts.insert("end", f"-- [{i+1}] {full_name} - HATA: {self._errors[i]}\n\n")
                
                self.progress_label.configure(text=f"✓ {len(self.all_scripts)}/{self._total} tablo hazır")
                self.progress_bar.set(1.0)
                self.btn_execute_all.configure(state="normal")
                self.btn_drop_all.configure(state="normal")
                self.btn_create_only.configure(state="normal")
                self.btn_transfer_data.configure(state="normal")
        
        # Arka plan thread'ini başlat
        self.progress_label.configure(text=f"Başlatılıyor ({total} tablo)...")
        thread = threading.Thread(target=background_generate, daemon=True)
        thread.start()
        
        # UI güncelleme döngüsünü başlat
        self.after(200, update_ui)
    
    def copy_scripts(self):
        """Scriptleri panoya kopyala"""
        text = self.txt_scripts.get("0.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Kopyalandı", "Tüm scriptler panoya kopyalandı.")
    
    def execute_all(self):
        """Tüm DROP + CREATE scriptlerini çalıştır"""
        if not self.all_scripts:
            messagebox.showerror("Hata", "Scriptler hazır değil.")
            return
        
        confirm = messagebox.askyesno(
            "⚠️ SON UYARI - GERİ ALINAMAZ!",
            f"{len(self.all_scripts)} tablo {self.target_name} veritabanında:\n\n"
            f"1. DROP TABLE ... CASCADE ile silinecek\n"
            f"2. CREATE TABLE ile yeniden oluşturulacak\n\n"
            f"TÜM VERİLER KAYBOLACAK!\n\n"
            f"Bu işlem GERİ ALINAMAZ. Devam?",
            icon="warning"
        )
        
        if not confirm:
            return
        
        self.btn_execute_all.configure(state="disabled", text="Çalıştırılıyor...")
        self.btn_drop_all.configure(state="disabled")
        
        success_count = 0
        error_count = 0
        error_details = []  # Hata detayları
        success_tables = []  # Başarılı tablolar
        
        for i, script in enumerate(self.all_scripts):
            self.progress_label.configure(text=f"Çalıştırılıyor: {script['full_name']} ({i+1}/{len(self.all_scripts)})")
            self.progress_bar.set((i + 1) / len(self.all_scripts))
            self.update()
            
            success, msg = logic.execute_migration(
                self.target_engine,
                script['drop_script'],
                script['create_script']
            )
            
            if success:
                success_count += 1
                success_tables.append(script['full_name'])
            else:
                error_count += 1
                error_details.append({
                    'table': script['full_name'],
                    'error': msg
                })
        
        self.progress_label.configure(text=f"✓ Tamamlandı: {success_count} başarılı, {error_count} hata")
        
        # Log dosyasına yaz
        from datetime import datetime
        log_file = f"migration_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== MİGRASYON RAPORU ===\n")
                f.write(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Kaynak: {self.source_name}\n")
                f.write(f"Hedef: {self.target_name}\n")
                f.write(f"Toplam: {len(self.all_scripts)} tablo\n")
                f.write(f"Başarılı: {success_count}\n")
                f.write(f"Hatalı: {error_count}\n\n")
                
                if error_details:
                    f.write("=== HATALI TABLOLAR ===\n\n")
                    for err in error_details:
                        f.write(f"❌ {err['table']}\n")
                        f.write(f"   Hata: {err['error']}\n\n")
                
                f.write("\n=== BAŞARILI TABLOLAR ===\n\n")
                for tbl in success_tables:
                    f.write(f"✓ {tbl}\n")
            
            print(f"[LOG] Migrasyon raporu yazıldı: {log_file}")
        except Exception as e:
            print(f"[LOG] Log dosyası yazılamadı: {e}")
        
        if error_count == 0:
            messagebox.showinfo("Başarılı", f"✓ Tüm tablolar ({success_count}) başarıyla aktarıldı!\n\nLog: {log_file}")
            self.btn_execute_all.configure(text="✓ Tamamlandı", fg_color=COLORS["success"])
        else:
            # Hata detaylarını göster
            error_summary = "\n".join([f"• {e['table']}: {e['error'][:50]}..." for e in error_details[:10]])
            if len(error_details) > 10:
                error_summary += f"\n... ve {len(error_details) - 10} hata daha"
            
            messagebox.showwarning(
                "Kısmi Başarı", 
                f"Başarılı: {success_count}, Hatalı: {error_count}\n\n"
                f"Hatalı Tablolar:\n{error_summary}\n\n"
                f"Detaylı log: {log_file}"
            )
            self.btn_execute_all.configure(text=f"{success_count}/{len(self.all_scripts)}", fg_color=COLORS["warning"])
    
    def drop_all(self):
        """Sadece DROP scriptlerini çalıştır"""
        if not self.all_scripts:
            messagebox.showerror("Hata", "Scriptler hazır değil.")
            return
        
        confirm = messagebox.askyesno(
            "⚠️ TABLOLAR SİLİNECEK!",
            f"{len(self.all_scripts)} tablo {self.target_name} veritabanında\n"
            f"DROP TABLE ... CASCADE ile SİLİNECEK!\n\n"
            f"Tablolar yeniden OLUŞTURULMAYACAK!\n"
            f"TÜM VERİLER KAYBOLACAK!\n\n"
            f"Bu işlem GERİ ALINAMAZ. Devam?",
            icon="warning"
        )
        
        if not confirm:
            return
        
        self.btn_drop_all.configure(state="disabled", text="Siliniyor...")
        self.btn_execute_all.configure(state="disabled")
        
        success_count = 0
        error_count = 0
        
        for i, script in enumerate(self.all_scripts):
            self.progress_label.configure(text=f"Siliniyor: {script['full_name']} ({i+1}/{len(self.all_scripts)})")
            self.progress_bar.set((i + 1) / len(self.all_scripts))
            self.update()
            
            success, msg = logic.execute_migration(
                self.target_engine,
                script['drop_script'],
                None  # CREATE yok
            )
            
            if success:
                success_count += 1
            else:
                error_count += 1
        
        self.progress_label.configure(text=f"✓ Silindi: {success_count}, Hata: {error_count}")
        
        if error_count == 0:
            messagebox.showinfo("Başarılı", f"✓ {success_count} tablo silindi!")
            self.btn_drop_all.configure(text="✓ Silindi", fg_color=COLORS["text_muted"])
        else:
            messagebox.showwarning("Kısmi Başarı", f"Silinen: {success_count}, Hatalı: {error_count}")
            self.btn_drop_all.configure(text=f"{success_count}/{len(self.all_scripts)}", fg_color=COLORS["warning"])
    
    def create_only(self):
        """Sadece CREATE scriptlerini çalıştır (DROP yapmadan)"""
        if not self.all_scripts:
            messagebox.showerror("Hata", "Scriptler hazır değil.")
            return
        
        confirm = messagebox.askyesno(
            "➕ SADECE CREATE",
            f"{len(self.all_scripts)} tablo {self.target_name} veritabanında\n"
            f"CREATE TABLE ile OLUŞTURULACAK.\n\n"
            f"Tablolar SİLİNMEYECEK, mevcut tablolar varsa HATA alınır.\n\n"
            f"Devam etmek istiyor musunuz?",
            icon="question"
        )
        
        if not confirm:
            return
        
        self.btn_create_only.configure(state="disabled", text="Oluşturuluyor...")
        self.btn_execute_all.configure(state="disabled")
        self.btn_drop_all.configure(state="disabled")
        
        success_count = 0
        error_count = 0
        error_details = []
        
        for i, script in enumerate(self.all_scripts):
            self.progress_label.configure(text=f"Oluşturuluyor: {script['full_name']} ({i+1}/{len(self.all_scripts)})")
            self.progress_bar.set((i + 1) / len(self.all_scripts))
            self.update()
            
            # Sadece CREATE çalıştır (DROP yok)
            success, msg = logic.execute_migration(
                self.target_engine,
                None,  # DROP yok
                script['create_script']
            )
            
            if success:
                success_count += 1
            else:
                error_count += 1
                error_details.append({'table': script['full_name'], 'error': msg})
        
        self.progress_label.configure(text=f"✓ Oluşturuldu: {success_count}, Hata: {error_count}")
        
        # Log dosyasına yaz
        from datetime import datetime
        log_file = f"create_only_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== SADECE CREATE RAPORU ===\n")
                f.write(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Hedef: {self.target_name}\n")
                f.write(f"Başarılı: {success_count}\n")
                f.write(f"Hatalı: {error_count}\n\n")
                
                if error_details:
                    f.write("=== HATALI TABLOLAR ===\n\n")
                    for err in error_details:
                        f.write(f"❌ {err['table']}\n")
                        f.write(f"   Hata: {err['error']}\n\n")
            print(f"[LOG] Create-only raporu: {log_file}")
        except:
            pass
        
        if error_count == 0:
            messagebox.showinfo("Başarılı", f"✓ {success_count} tablo oluşturuldu!\n\nLog: {log_file}")
            self.btn_create_only.configure(text="✓ Oluşturuldu", fg_color=COLORS["success"])
        else:
            error_summary = "\n".join([f"• {e['table']}: {e['error'][:40]}..." for e in error_details[:5]])
            messagebox.showwarning(
                "Kısmi Başarı", 
                f"Oluşturulan: {success_count}, Hatalı: {error_count}\n\n"
                f"Hatalı Tablolar:\n{error_summary}\n\n"
                f"Log: {log_file}"
            )
            self.btn_create_only.configure(text=f"{success_count}/{len(self.all_scripts)}", fg_color=COLORS["warning"])
        
        self.btn_execute_all.configure(state="normal")
        self.btn_drop_all.configure(state="normal")
    
    def transfer_all_data(self):
        """Tüm tabloların verilerini kaynak DB'den hedef DB'ye aktar"""
        if not self.all_scripts:
            messagebox.showerror("Hata", "Tablo listesi hazır değil.")
            return
        
        confirm = messagebox.askyesno(
            "📤 VERİ AKTARIMI",
            f"{len(self.all_scripts)} tablonun verileri\n"
            f"{self.source_name} → {self.target_name}\n\n"
            f"aktarılacak. Hedef tablolardaki mevcut veriler korunacak,\n"
            f"kaynak tablodaki veriler eklenecek.\n\n"
            f"Devam etmek istiyor musunuz?",
            icon="question"
        )
        
        if not confirm:
            return
        
        self.btn_transfer_data.configure(state="disabled", text="Aktarılıyor...")
        self.btn_execute_all.configure(state="disabled")
        self.btn_drop_all.configure(state="disabled")
        
        success_count = 0
        error_count = 0
        error_details = []
        total_rows = 0
        
        for i, script in enumerate(self.all_scripts):
            schema = script['schema']
            table_name = script['table_name']
            full_name = script['full_name']
            
            self.progress_label.configure(text=f"Aktarılıyor: {full_name} ({i+1}/{len(self.all_scripts)})")
            self.progress_bar.set((i + 1) / len(self.all_scripts))
            self.update()
            
            try:
                # Kaynak tablodan veri çek
                import pandas as pd
                if schema:
                    query = f'SELECT * FROM "{schema}"."{table_name}"'
                else:
                    query = f'SELECT * FROM "{table_name}"'
                
                df = pd.read_sql(query, self.source_engine)
                
                if len(df) == 0:
                    success_count += 1
                    continue
                
                # Hedef tabloya yaz
                target_table = table_name
                df.to_sql(
                    target_table, 
                    self.target_engine, 
                    schema=schema,
                    if_exists='append',  # Mevcut verilere ekle
                    index=False,
                    method='multi',
                    chunksize=1000
                )
                
                success_count += 1
                total_rows += len(df)
                
            except Exception as e:
                error_count += 1
                error_details.append({
                    'table': full_name,
                    'error': str(e)
                })
        
        self.progress_label.configure(text=f"✓ Aktarıldı: {success_count} tablo, {total_rows} satır")
        
        # Log dosyasına yaz
        from datetime import datetime
        log_file = f"data_transfer_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"=== VERİ AKTARIM RAPORU ===\n")
                f.write(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Kaynak: {self.source_name}\n")
                f.write(f"Hedef: {self.target_name}\n")
                f.write(f"Toplam Tablo: {len(self.all_scripts)}\n")
                f.write(f"Başarılı: {success_count}\n")
                f.write(f"Hatalı: {error_count}\n")
                f.write(f"Toplam Satır: {total_rows}\n\n")
                
                if error_details:
                    f.write("=== HATALI TABLOLAR ===\n\n")
                    for err in error_details:
                        f.write(f"❌ {err['table']}\n")
                        f.write(f"   Hata: {err['error']}\n\n")
            
            print(f"[LOG] Veri aktarım raporu: {log_file}")
        except Exception as e:
            print(f"[LOG] Log yazılamadı: {e}")
        
        if error_count == 0:
            messagebox.showinfo("Başarılı", 
                f"✓ Veri aktarımı tamamlandı!\n\n"
                f"Tablo: {success_count}\n"
                f"Satır: {total_rows}\n\n"
                f"Log: {log_file}")
            self.btn_transfer_data.configure(text="✓ Aktarıldı", fg_color=COLORS["success"])
        else:
            error_summary = "\n".join([f"• {e['table']}: {e['error'][:40]}..." for e in error_details[:5]])
            messagebox.showwarning("Kısmi Başarı", 
                f"Başarılı: {success_count}, Hatalı: {error_count}\n\n"
                f"Hatalı Tablolar:\n{error_summary}\n\n"
                f"Log: {log_file}")
            self.btn_transfer_data.configure(text=f"{success_count}/{len(self.all_scripts)}", fg_color=COLORS["warning"])
        
        self.btn_execute_all.configure(state="normal")
        self.btn_drop_all.configure(state="normal")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("DB Comparator")
        self.geometry("1400x900")
        self.configure(fg_color=COLORS["bg_primary"])

        # State
        self.discovered_tables = []  # Keşfedilen tablolar
        self.selected_tables = {}    # full_name -> table_info (seçili tablolar)
        self.manual_tables = []      # Manuel eklenen tablolar
        self.comparison_results = []
        self.engine1 = None
        self.engine2 = None
        self.db1_name = ""
        self.db2_name = ""
        self.current_phase = "discovery"  # discovery veya comparison
        self.current_view = "discovery"   # discovery veya comparison (görünüm için)

        # Grid Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- SOL PANEL ---
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=COLORS["bg_secondary"])
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(20, weight=1)  # En alt row genişleyebilir
        self.sidebar_frame.grid_propagate(False)

        # Logo
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="DB Comparator", 
            font=ctk.CTkFont(size=20, weight="bold"), text_color=COLORS["text_primary"])
        self.logo_label.grid(row=0, column=0, padx=20, pady=(25, 5))
        
        self.subtitle_label = ctk.CTkLabel(self.sidebar_frame, text="Veritabanı Karşılaştırma Aracı", 
            font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"])
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # Kayıtlı Bağlantılar
        self.lbl_saved = ctk.CTkLabel(self.sidebar_frame, text="Kayıtlı Bağlantılar", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["text_secondary"])
        self.lbl_saved.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.saved_connections = self.load_saved_connections()
        self.saved_combo = ctk.CTkComboBox(self.sidebar_frame, values=self.get_saved_names(),
            state="readonly", command=self.on_saved_connection_select, height=36,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], text_color=COLORS["text_primary"])
        self.saved_combo.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")
        if self.saved_connections:
            self.saved_combo.set("Seçiniz...")
        else:
            self.saved_combo.set("Kayıtlı bağlantı yok")

        # DB1 Ayarları
        self.lbl_db1 = ctk.CTkLabel(self.sidebar_frame, text="Kaynak Veritabanı", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["text_secondary"])
        self.lbl_db1.grid(row=4, column=0, padx=20, pady=(10, 5), sticky="w")
        
        self.entry_db1_name = ctk.CTkEntry(self.sidebar_frame, placeholder_text="İsim (örn: Stage)", height=36,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"])
        self.entry_db1_name.grid(row=5, column=0, padx=20, pady=(0, 4), sticky="ew")

        self.entry_db1_url = ctk.CTkEntry(self.sidebar_frame, placeholder_text="User ID=...;Password=...;Host=...;Port=...;Database=...", height=36,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"])
        self.entry_db1_url.grid(row=6, column=0, padx=20, pady=(0, 4), sticky="ew")
        
        # DB1 Buton satırı (Test + Kaynak Tipi)
        self.db1_btn_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.db1_btn_frame.grid(row=7, column=0, padx=20, pady=(0, 4), sticky="ew")
        
        self.btn_test_db1 = ctk.CTkButton(self.db1_btn_frame, text="Test", width=50,
            command=lambda: self.test_connection(1), fg_color=COLORS["bg_card"], 
            hover_color=COLORS["border"], height=26, font=ctk.CTkFont(size=10))
        self.btn_test_db1.pack(side="left")
        
        self.db1_source_var = ctk.StringVar(value="db")
        self.db1_source_db = ctk.CTkRadioButton(self.db1_btn_frame, text="DB", variable=self.db1_source_var,
            value="db", command=self.on_db1_source_change, font=ctk.CTkFont(size=10),
            fg_color=COLORS["accent"], text_color=COLORS["text_secondary"])
        self.db1_source_db.pack(side="left", padx=(10, 0))
        
        self.db1_source_file = ctk.CTkRadioButton(self.db1_btn_frame, text="Dosya", variable=self.db1_source_var,
            value="file", command=self.on_db1_source_change, font=ctk.CTkFont(size=10),
            fg_color=COLORS["accent"], text_color=COLORS["text_secondary"])
        self.db1_source_file.pack(side="left", padx=(5, 0))
        
        # DB1 Snapshot seçici (başlangıçta gizli)
        self.db1_snapshot_combo = ctk.CTkComboBox(self.sidebar_frame, values=["Snapshot seçin..."],
            state="readonly", height=32, font=ctk.CTkFont(size=10), command=self.on_db1_snapshot_select,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], text_color=COLORS["text_primary"])
        self.db1_snapshot_path = None

        # DB2 Ayarları
        self.lbl_db2 = ctk.CTkLabel(self.sidebar_frame, text="Hedef Veritabanı", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["text_secondary"])
        self.lbl_db2.grid(row=8, column=0, padx=20, pady=(5, 5), sticky="w")
        
        self.entry_db2_name = ctk.CTkEntry(self.sidebar_frame, placeholder_text="İsim (örn: Sandbox)", height=36,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"])
        self.entry_db2_name.grid(row=9, column=0, padx=20, pady=(0, 4), sticky="ew")

        self.entry_db2_url = ctk.CTkEntry(self.sidebar_frame, placeholder_text="User ID=...;Password=...;Host=...;Port=...;Database=...", height=36,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"])
        self.entry_db2_url.grid(row=10, column=0, padx=20, pady=(0, 4), sticky="ew")
        
        # DB2 Buton satırı (Test + Kaynak Tipi)
        self.db2_btn_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.db2_btn_frame.grid(row=11, column=0, padx=20, pady=(0, 4), sticky="ew")
        
        self.btn_test_db2 = ctk.CTkButton(self.db2_btn_frame, text="Test", width=50,
            command=lambda: self.test_connection(2), fg_color=COLORS["bg_card"], 
            hover_color=COLORS["border"], height=26, font=ctk.CTkFont(size=10))
        self.btn_test_db2.pack(side="left")
        
        self.db2_source_var = ctk.StringVar(value="db")
        self.db2_source_db = ctk.CTkRadioButton(self.db2_btn_frame, text="DB", variable=self.db2_source_var,
            value="db", command=self.on_db2_source_change, font=ctk.CTkFont(size=10),
            fg_color=COLORS["accent"], text_color=COLORS["text_secondary"])
        self.db2_source_db.pack(side="left", padx=(10, 0))
        
        self.db2_source_file = ctk.CTkRadioButton(self.db2_btn_frame, text="Dosya", variable=self.db2_source_var,
            value="file", command=self.on_db2_source_change, font=ctk.CTkFont(size=10),
            fg_color=COLORS["accent"], text_color=COLORS["text_secondary"])
        self.db2_source_file.pack(side="left", padx=(5, 0))
        
        # DB2 Snapshot seçici (başlangıçta gizli)
        self.db2_snapshot_combo = ctk.CTkComboBox(self.sidebar_frame, values=["Snapshot seçin..."],
            state="readonly", height=32, font=ctk.CTkFont(size=10), command=self.on_db2_snapshot_select,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], text_color=COLORS["text_primary"])
        self.db2_snapshot_path = None
        
        # Kaydet butonu
        self.btn_save_connection = ctk.CTkButton(self.sidebar_frame, text="Bu Bağlantıyı Kaydet",
            command=self.save_current_connection, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=32, font=ctk.CTkFont(size=12), text_color=COLORS["bg_primary"])
        self.btn_save_connection.grid(row=12, column=0, padx=20, pady=(5, 15), sticky="ew")

        # Karşılaştırma Modu
        self.lbl_mode = ctk.CTkLabel(self.sidebar_frame, text="Karşılaştırma Modu", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=COLORS["text_secondary"])
        self.lbl_mode.grid(row=13, column=0, padx=20, pady=(5, 5), sticky="w")
        
        self._selected_mode = "SYMMETRIC"
        self.mode_combobox = ctk.CTkComboBox(self.sidebar_frame, values=self._get_mode_options(),
            state="readonly", command=self._on_mode_change, height=36,
            border_color=COLORS["border"], fg_color=COLORS["input_bg"], button_color=COLORS["border"],
            button_hover_color=COLORS["accent"], dropdown_fg_color=COLORS["bg_secondary"], text_color=COLORS["text_primary"])
        self.mode_combobox.grid(row=14, column=0, padx=20, pady=(0, 20), sticky="ew")
        
        self.entry_db1_name.bind("<KeyRelease>", self._update_mode_options)
        self.entry_db2_name.bind("<KeyRelease>", self._update_mode_options)

        # ADIM 1: Tabloları Tara Butonu
        self.btn_scan = ctk.CTkButton(self.sidebar_frame, text="1. Tabloları Tara", 
            command=self.start_discovery_thread, height=44, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"], corner_radius=8)
        self.btn_scan.grid(row=15, column=0, padx=20, pady=(10, 8), sticky="ew")

        # ADIM 2: Karşılaştır Butonu
        self.btn_compare = ctk.CTkButton(self.sidebar_frame, text="2. Karşılaştır", 
            command=self.start_comparison_thread, height=44, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"], text_color=COLORS["text_muted"], 
            corner_radius=8, state="disabled")
        self.btn_compare.grid(row=16, column=0, padx=20, pady=(0, 8), sticky="ew")

        # Excel Raporu Aç
        self.btn_open_report = ctk.CTkButton(self.sidebar_frame, text="Excel Raporu Aç", 
            command=self.open_report, fg_color=COLORS["bg_card"], hover_color=COLORS["border"],
            state="disabled", height=40, font=ctk.CTkFont(size=13), corner_radius=8, text_color=COLORS["text_primary"])
        self.btn_open_report.grid(row=17, column=0, padx=20, pady=(0, 10), sticky="ew")
        
        # Bilgi (en alta sabit)
        self.lbl_info = ctk.CTkLabel(self.sidebar_frame, 
            text="1) Önce tabloları tarayın\n2) Listeyi düzenleyin\n3) Karşılaştırmayı başlatın", 
            font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"], justify="left")
        self.lbl_info.grid(row=21, column=0, padx=20, pady=(10, 15), sticky="sw")

        # --- SAĞ PANEL ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["bg_primary"])
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(2, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Durum Kartı
        self.status_card = ctk.CTkFrame(self.main_frame, fg_color=COLORS["bg_secondary"], corner_radius=12)
        self.status_card.grid(row=0, column=0, padx=20, pady=(20, 15), sticky="ew")
        self.status_card.grid_columnconfigure(0, weight=1)
        
        self.status_top = ctk.CTkFrame(self.status_card, fg_color="transparent")
        self.status_top.pack(fill="x", padx=20, pady=(15, 10))
        
        self.lbl_status = ctk.CTkLabel(self.status_top, text="Hazır", 
            font=ctk.CTkFont(size=18, weight="bold"), text_color=COLORS["text_primary"])
        self.lbl_status.pack(side="left")
        
        self.progressbar = ctk.CTkProgressBar(self.status_top, orientation="horizontal",
            progress_color=COLORS["accent"], fg_color=COLORS["bg_card"], height=6, width=150)
        self.progressbar.pack(side="right")
        self.progressbar.set(0)
        
        self.lbl_status_desc = ctk.CTkLabel(self.status_card, text="Tabloları taramak için butona tıklayın", 
            font=ctk.CTkFont(size=11), text_color=COLORS["text_muted"], anchor="w")
        self.lbl_status_desc.pack(fill="x", padx=20, pady=(0, 5))
        
        self.stats_frame = ctk.CTkFrame(self.status_card, fg_color="transparent")
        self.stats_frame.pack(fill="x", padx=15, pady=(5, 15))
        self.stat_cards = []

        # Tablo Listesi Araç Çubuğu
        self.toolbar_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.toolbar_frame.grid(row=1, column=0, padx=20, pady=(5, 5), sticky="ew")
        
        self.table_header = ctk.CTkLabel(self.toolbar_frame, text="Bulunan Tanım Tabloları", 
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLORS["text_primary"])
        self.table_header.pack(side="left")
        
        # Manuel Ekleme/Silme Butonları
        self.btn_remove_table = ctk.CTkButton(self.toolbar_frame, text="Seçileni Sil", width=100,
            command=self.remove_selected_table, fg_color=COLORS["error"], hover_color="#ef5350",
            height=32, font=ctk.CTkFont(size=12), state="disabled")
        self.btn_remove_table.pack(side="right", padx=5)
        
        self.btn_add_table = ctk.CTkButton(self.toolbar_frame, text="Manuel Ekle", width=100,
            command=self.add_manual_table, fg_color=COLORS["success"], hover_color="#66bb6a",
            height=32, font=ctk.CTkFont(size=12), state="disabled")
        self.btn_add_table.pack(side="right", padx=5)
        
        # Görünüm Değiştir / Geri Butonu
        self.btn_toggle_view = ctk.CTkButton(self.toolbar_frame, text="Sonuçları Göster", width=120,
            command=self.toggle_view, fg_color=COLORS["bg_card"], hover_color=COLORS["border"],
            height=32, font=ctk.CTkFont(size=12), state="disabled", text_color=COLORS["text_primary"])
        self.btn_toggle_view.pack(side="right", padx=5)
        
        # Yapı Aktarımı Butonu (tek tablo)
        self.btn_migrate_structure = ctk.CTkButton(self.toolbar_frame, text="📦 Yapıyı Aktar", width=120,
            command=self.open_migration_dialog, fg_color=COLORS["warning"], hover_color="#ffa726",
            height=32, font=ctk.CTkFont(size=12), state="disabled", text_color=COLORS["bg_primary"])
        self.btn_migrate_structure.pack(side="right", padx=5)
        
        # Toplu İşlem Butonu (yeni)
        self.btn_bulk_migrate = ctk.CTkButton(self.toolbar_frame, text="⚡ Toplu İşlem", width=110,
            command=self.open_bulk_migration_dialog, fg_color=COLORS["error"], hover_color="#ef5350",
            height=32, font=ctk.CTkFont(size=12), state="disabled", text_color="white")
        self.btn_bulk_migrate.pack(side="right", padx=5)
        
        # Toplu Veri Aktar Butonu
        self.btn_bulk_data = ctk.CTkButton(self.toolbar_frame, text="📤 Toplu Veri Aktar", width=130,
            command=self.open_bulk_data_transfer, fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=32, font=ctk.CTkFont(size=12), state="disabled", text_color=COLORS["bg_primary"])
        self.btn_bulk_data.pack(side="right", padx=5)
        
        # Tümünü Seç / Seçimi Kaldır Butonu
        self.btn_select_all = ctk.CTkButton(self.toolbar_frame, text="☑ Tümünü Seç", width=100,
            command=self.toggle_select_all, fg_color=COLORS["bg_card"], hover_color=COLORS["border"],
            height=32, font=ctk.CTkFont(size=12), state="disabled", text_color=COLORS["text_primary"])
        self.btn_select_all.pack(side="right", padx=5)

        # Tablo Listesi
        self.tree_frame = ctk.CTkFrame(self.main_frame, fg_color=COLORS["bg_secondary"], corner_radius=12)
        self.tree_frame.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="nsew")
        
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Soft.Treeview", background=COLORS["bg_card"], foreground=COLORS["text_primary"], 
            fieldbackground=COLORS["bg_card"], rowheight=28, font=('Segoe UI', 10))
        style.configure("Soft.Treeview.Heading", background=COLORS["bg_secondary"], 
            foreground=COLORS["text_secondary"], font=('Segoe UI', 10, 'bold'), relief="flat")
        style.map("Soft.Treeview", background=[('selected', COLORS["accent"])])
        
        self.tree_columns = ("Şema", "Tablo", "Kaynak", "Durum")
        self.tree = ttk.Treeview(self.tree_frame, columns=self.tree_columns, show="headings", 
            height=16, style="Soft.Treeview")
        
        self.tree.heading("Şema", text="Şema")
        self.tree.heading("Tablo", text="Tablo")
        self.tree.heading("Kaynak", text="Kaynak")
        self.tree.heading("Durum", text="Durum")
        
        self.tree.column("Şema", width=150)
        self.tree.column("Tablo", width=250)
        self.tree.column("Kaynak", width=120)
        self.tree.column("Durum", width=200)
        
        self.tree.pack(side="left", fill="both", expand=True, padx=12, pady=12)
        
        self.tree_scroll = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        self.tree_scroll.pack(side="right", fill="y", pady=12, padx=(0, 12))
        self.tree.configure(yscrollcommand=self.tree_scroll.set)
        
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Button-3>", self.on_tree_right_click)  # Sağ tık menüsü
        
        # Sağ tık context menüsü
        self.context_menu = None
        
        # Arama Paneli (toolbar içinde, başlangıçta gizli)
        self.search_container = ctk.CTkFrame(self.toolbar_frame, fg_color="transparent")
        self.search_visible = False
        self.search_matches = []  # Eşleşen satırların ID'leri
        self.search_index = -1    # Şu anki sonuç indeksi
        
        self.search_entry = ctk.CTkEntry(self.search_container, placeholder_text="🔍 Ara...",
            width=180, height=30, fg_color=COLORS["input_bg"], border_color=COLORS["accent"],
            text_color=COLORS["text_primary"])
        self.search_entry.pack(side="left", padx=(0, 5))
        self.search_entry.bind("<KeyRelease>", self.on_search_key)
        self.search_entry.bind("<Escape>", lambda e: self.toggle_search())
        self.search_entry.bind("<Return>", self.on_search_enter)
        # CTkEntry iç widget'a da bind
        try:
            self.search_entry._entry.bind("<Return>", self.on_search_enter)
        except:
            pass
        
        # Yukarı/Aşağı butonları
        self.btn_search_up = ctk.CTkButton(self.search_container, text="▲", width=28, height=28,
            command=self.search_prev, fg_color=COLORS["bg_secondary"], hover_color=COLORS["accent"])
        self.btn_search_up.pack(side="left", padx=1)
        
        self.btn_search_down = ctk.CTkButton(self.search_container, text="▼", width=28, height=28,
            command=self.search_next, fg_color=COLORS["bg_secondary"], hover_color=COLORS["accent"])
        self.btn_search_down.pack(side="left", padx=1)
        
        self.search_count_label = ctk.CTkLabel(self.search_container, text="", 
            font=ctk.CTkFont(size=10), text_color=COLORS["text_secondary"], width=70)
        self.search_count_label.pack(side="left", padx=5)
        
        self.btn_search_close = ctk.CTkButton(self.search_container, text="✕", width=28, height=28,
            command=self.toggle_search, fg_color=COLORS["bg_secondary"], hover_color=COLORS["error"])
        self.btn_search_close.pack(side="left")
        
        # Ctrl+F kısayolu
        self.bind("<Control-f>", lambda e: self.toggle_search())
        self.bind("<Control-F>", lambda e: self.toggle_search())

        # Log Alanı
        self.log_label = ctk.CTkLabel(self.main_frame, text="İşlem Logları", anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=COLORS["text_primary"])
        self.log_label.grid(row=3, column=0, padx=25, pady=(10, 5), sticky="w")
        
        self.textbox = ctk.CTkTextbox(self.main_frame, height=100, font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=COLORS["bg_secondary"], text_color=COLORS["text_secondary"], corner_radius=10)
        self.textbox.grid(row=4, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.textbox.insert("0.0", "Uygulama başlatıldı.\n1) Sol panelden veritabanı bilgilerini girin\n2) 'Tabloları Tara' butonuna tıklayın\n")
        
        self._mode_mapping = {}
        self._update_mode_options(None)

    def _get_mode_options(self):
        db1 = self.entry_db1_name.get() or "DB1"
        db2 = self.entry_db2_name.get() or "DB2"
        return ["Simetrik (İki Yönlü)", f"{db1} → {db2} Eksikleri", f"{db2} → {db1} Eksikleri"]
    
    def _update_mode_options(self, event):
        options = self._get_mode_options()
        self.mode_combobox.configure(values=options)
        self._mode_mapping = {options[0]: "SYMMETRIC", options[1]: "DB1", options[2]: "DB2"}
        current = self.mode_combobox.get()
        if current not in options:
            self.mode_combobox.set(options[0])
    
    def _on_mode_change(self, choice):
        self._selected_mode = self._mode_mapping.get(choice, "SYMMETRIC")

    # ========== BAĞLANTI YÖNETİMİ ==========
    def load_saved_connections(self):
        """Kayıtlı bağlantıları dosyadan yükle"""
        try:
            if os.path.exists(SAVED_CONNECTIONS_FILE):
                with open(SAVED_CONNECTIONS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Bağlantılar yüklenemedi: {e}")
        return []
    
    def save_connections_to_file(self):
        """Bağlantıları dosyaya kaydet"""
        try:
            with open(SAVED_CONNECTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.saved_connections, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Bağlantılar kaydedilemedi: {e}")
    
    def get_saved_names(self):
        """Kayıtlı bağlantı isimlerini döndür"""
        return [conn['name'] for conn in self.saved_connections] if self.saved_connections else []
    
    def on_saved_connection_select(self, choice):
        """Kayıtlı bağlantı seçildiğinde alanları doldur"""
        for conn in self.saved_connections:
            if conn['name'] == choice:
                # Alanları temizle ve doldur
                self.entry_db1_name.delete(0, 'end')
                self.entry_db1_name.insert(0, conn.get('db1_name', ''))
                
                self.entry_db1_url.delete(0, 'end')
                self.entry_db1_url.insert(0, conn.get('db1_url', ''))
                
                self.entry_db2_name.delete(0, 'end')
                self.entry_db2_name.insert(0, conn.get('db2_name', ''))
                
                self.entry_db2_url.delete(0, 'end')
                self.entry_db2_url.insert(0, conn.get('db2_url', ''))
                
                self._update_mode_options(None)
                self.log(f"Bağlantı yüklendi: {choice}")
                break
    
    def save_current_connection(self):
        """Mevcut bağlantıyı kaydet"""
        db1_name = self.entry_db1_name.get().strip()
        db2_name = self.entry_db2_name.get().strip()
        db1_url = self.entry_db1_url.get().strip()
        db2_url = self.entry_db2_url.get().strip()
        
        if not db1_name or not db2_name or not db1_url or not db2_url:
            messagebox.showwarning("Uyarı", "Lütfen tüm alanları doldurun.")
            return
        
        # Bağlantı adı oluştur
        conn_name = f"{db1_name} ↔ {db2_name}"
        
        # Aynı isimde varsa güncelle
        existing_idx = None
        for i, conn in enumerate(self.saved_connections):
            if conn['name'] == conn_name:
                existing_idx = i
                break
        
        new_conn = {
            'name': conn_name,
            'db1_name': db1_name,
            'db1_url': db1_url,
            'db2_name': db2_name,
            'db2_url': db2_url
        }
        
        if existing_idx is not None:
            self.saved_connections[existing_idx] = new_conn
            self.log(f"Bağlantı güncellendi: {conn_name}")
        else:
            self.saved_connections.append(new_conn)
            self.log(f"Bağlantı kaydedildi: {conn_name}")
        
        self.save_connections_to_file()
        self.saved_combo.configure(values=self.get_saved_names())
        self.saved_combo.set(conn_name)
        messagebox.showinfo("Başarılı", f"Bağlantı kaydedildi: {conn_name}")
    
    def test_connection(self, db_num):
        """Veritabanı bağlantısını test et"""
        if db_num == 1:
            url = self.entry_db1_url.get().strip()
            name = self.entry_db1_name.get() or "DB1"
            btn = self.btn_test_db1
        else:
            url = self.entry_db2_url.get().strip()
            name = self.entry_db2_name.get() or "DB2"
            btn = self.btn_test_db2
        
        if not url:
            messagebox.showwarning("Uyarı", "Bağlantı URL'si boş.")
            return
        
        btn.configure(state="disabled", text="...")
        self.update()
        
        try:
            engine = logic.get_db_engine(url)
            if engine:
                # Basit sorgu ile test et
                with engine.connect() as conn:
                    conn.execute(logic.text("SELECT 1"))
                btn.configure(text="✓", fg_color=COLORS["success"])
                self.log(f"✓ {name} bağlantısı başarılı")
                messagebox.showinfo("Başarılı", f"{name} bağlantısı başarılı!")
            else:
                btn.configure(text="✗", fg_color=COLORS["error"])
                self.log(f"✗ {name} bağlantısı başarısız")
                messagebox.showerror("Hata", f"{name} bağlantısı başarısız!")
        except Exception as e:
            btn.configure(text="✗", fg_color=COLORS["error"])
            self.log(f"✗ {name} bağlantısı hatası: {str(e)[:50]}")
            messagebox.showerror("Bağlantı Hatası", f"{name} bağlantısı başarısız:\n{str(e)[:100]}")
        finally:
            self.after(2000, lambda: self.reset_test_button(btn))

    # ========== ARAMA FONKSİYONLARI ==========
    def toggle_search(self):
        """Arama panelini aç/kapat"""
        if self.search_visible:
            self.search_container.pack_forget()
            self.search_visible = False
            self.search_entry.delete(0, "end")
            self.restore_all_rows()
        else:
            # Toolbar'ın en soluna yerleştir
            self.search_container.pack(side="left", padx=(0, 10))
            self.search_visible = True
            self.search_entry.focus()

    def on_search_key(self, event=None):
        """Tuş bırakıldığında - Enter hariç arama yap"""
        # Enter tuşunu atla (ayrı handler var)
        if event and event.keysym == "Return":
            return
        self.on_search_change()

    def on_search_enter(self, event=None):
        """Enter tuşuna basıldığında sonraki sonuca git"""
        if not self.search_matches:
            return "break"
        
        self.search_index = (self.search_index + 1) % len(self.search_matches)
        self.goto_search_result()
        return "break"

    def on_search_change(self, event=None):
        """Arama metni değiştiğinde"""
        query = self.search_entry.get().strip().lower()
        if len(query) >= 2:
            self.perform_search(query)
        else:
            self.restore_all_rows()
            self.search_count_label.configure(text="")
            self.search_matches = []
            self.search_index = -1

    def perform_search(self, query):
        """Tabloda arama yap ve eşleşenleri göster"""
        self.search_matches = []
        self.search_index = -1
        
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            row_text = " ".join(str(v).lower() for v in values)
            
            if query in row_text:
                self.tree.item(item, tags=("search_match",))
                self.search_matches.append(item)
            else:
                self.tree.item(item, tags=("search_nomatch",))
        
        # Renklendirme
        self.tree.tag_configure("search_match", foreground=COLORS["text_primary"])
        self.tree.tag_configure("search_nomatch", foreground=COLORS["border"])
        
        match_count = len(self.search_matches)
        if match_count > 0:
            self.search_index = 0
            self.goto_search_result()
            self.search_count_label.configure(text=f"1/{match_count}")
        else:
            self.search_count_label.configure(text="0 sonuç")

    def search_next(self):
        """Sonraki arama sonucuna git"""
        if not self.search_matches:
            return
        self.search_index = (self.search_index + 1) % len(self.search_matches)
        self.goto_search_result()

    def search_prev(self):
        """Önceki arama sonucuna git"""
        if not self.search_matches:
            return
        self.search_index = (self.search_index - 1) % len(self.search_matches)
        self.goto_search_result()

    def goto_search_result(self):
        """Mevcut arama sonucuna git ve seç"""
        if not self.search_matches or self.search_index < 0:
            return
        item = self.search_matches[self.search_index]
        
        # Seç ve focus ver
        self.tree.selection_set(item)
        self.tree.focus(item)
        
        # Sayacı güncelle
        self.search_count_label.configure(text=f"{self.search_index + 1}/{len(self.search_matches)}")
        
        # Gecikme ile görünür yap
        def scroll_to_item():
            self.tree.see(item)
            # Ek olarak yview ile kaydır
            try:
                all_items = self.tree.get_children()
                if item in all_items:
                    idx = list(all_items).index(item)
                    total = len(all_items)
                    if total > 0:
                        self.tree.yview_moveto(max(0, (idx - 3) / total))
            except:
                pass
        
        self.after(50, scroll_to_item)

    def restore_all_rows(self):
        """Tüm satırları normal görünüme döndür"""
        for item in self.tree.get_children():
            self.tree.item(item, tags=())

    def log(self, message):
        self.textbox.insert("end", message + "\n")
        self.textbox.see("end")

    def update_status(self, title, desc, color=None):
        self.lbl_status.configure(text=title, text_color=color or COLORS["text_primary"])
        self.lbl_status_desc.configure(text=desc)

    def reset_test_button(self, btn):
        """Test butonunu varsayılan haline döndür"""
        btn.configure(state="normal", text="Test", fg_color=COLORS["bg_card"])

    # ========== KAYNAK TİPİ DEĞİŞTİRME ==========
    def on_db1_source_change(self):
        """DB1 kaynak tipi değiştiğinde"""
        if self.db1_source_var.get() == "file":
            # URL'yi gizle, snapshot combo'yu göster
            self.refresh_snapshot_list(1)
            self.entry_db1_url.grid_forget()
            self.db1_snapshot_combo.grid(row=6, column=0, padx=20, pady=(0, 4), sticky="ew")
            self.btn_test_db1.configure(state="disabled")
        else:
            # Snapshot combo'yu gizle, URL'yi göster
            self.db1_snapshot_combo.grid_forget()
            self.entry_db1_url.grid(row=6, column=0, padx=20, pady=(0, 4), sticky="ew")
            self.btn_test_db1.configure(state="normal")
            self.db1_snapshot_path = None
        self.check_file_to_file_mode()

    def on_db2_source_change(self):
        """DB2 kaynak tipi değiştiğinde"""
        if self.db2_source_var.get() == "file":
            self.refresh_snapshot_list(2)
            self.entry_db2_url.grid_forget()
            self.db2_snapshot_combo.grid(row=10, column=0, padx=20, pady=(0, 4), sticky="ew")
            self.btn_test_db2.configure(state="disabled")
        else:
            self.db2_snapshot_combo.grid_forget()
            self.entry_db2_url.grid(row=10, column=0, padx=20, pady=(0, 4), sticky="ew")
            self.btn_test_db2.configure(state="normal")
            self.db2_snapshot_path = None
        self.check_file_to_file_mode()

    def check_file_to_file_mode(self):
        """Her iki kaynak da dosya ise karşılaştır butonunu aktif et"""
        db1_is_file = self.db1_source_var.get() == "file"
        db2_is_file = self.db2_source_var.get() == "file"
        
        if db1_is_file and db2_is_file:
            # Her iki kaynak da dosya - taramaya gerek yok, direkt karşılaştırma
            self.btn_scan.configure(text="1. Tabloları Tara (Opsiyonel)")
            self.btn_compare.configure(
                state="normal", 
                fg_color=COLORS["accent"], 
                hover_color=COLORS["accent_hover"], 
                text_color=COLORS["bg_primary"]
            )
            self.log("Her iki kaynak da dosya - doğrudan karşılaştırma yapabilirsiniz.")
        else:
            self.btn_scan.configure(text="1. Tabloları Tara")
            # Eğer discovery yapılmadıysa karşılaştır butonunu pasif et
            if not self.selected_tables:
                self.btn_compare.configure(
                    state="disabled", 
                    fg_color=COLORS["bg_card"], 
                    text_color=COLORS["text_muted"]
                )

    def refresh_snapshot_list(self, db_num):
        """Snapshot listesini güncelle"""
        snapshots = logic.list_snapshots()
        if snapshots:
            names = [f"{s[2].get('db_name', 'Bilinmeyen')} - {s[2].get('created_at', '')[:10]}" for s in snapshots]
            self.snapshot_map = {name: s[1] for name, s in zip(names, snapshots)}
        else:
            names = ["Snapshot bulunamadı"]
            self.snapshot_map = {}
        
        if db_num == 1:
            self.db1_snapshot_combo.configure(values=names)
            self.db1_snapshot_combo.set(names[0] if names else "")
        else:
            self.db2_snapshot_combo.configure(values=names)
            self.db2_snapshot_combo.set(names[0] if names else "")

    def on_db1_snapshot_select(self, choice):
        """DB1 snapshot seçildiğinde"""
        if choice in self.snapshot_map:
            self.db1_snapshot_path = self.snapshot_map[choice]
            self.log(f"DB1 snapshot seçildi: {choice}")

    def on_db2_snapshot_select(self, choice):
        """DB2 snapshot seçildiğinde"""
        if choice in self.snapshot_map:
            self.db2_snapshot_path = self.snapshot_map[choice]
            self.log(f"DB2 snapshot seçildi: {choice}")

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if selected and self.current_phase == "discovery" and self.current_view == "discovery":
            self.btn_remove_table.configure(state="normal")
        else:
            self.btn_remove_table.configure(state="disabled")
        
        # Migrasyon butonu için - karşılaştırma sonuçlarında aktif
        if selected and self.engine1 and self.engine2:
            self.btn_migrate_structure.configure(state="normal")
        else:
            self.btn_migrate_structure.configure(state="disabled")
        
        # Toplu işlem ve tümünü seç butonları
        if self.engine1 and self.engine2 and len(self.tree.get_children()) > 0:
            self.btn_bulk_migrate.configure(state="normal")
            self.btn_bulk_data.configure(state="normal")
            self.btn_select_all.configure(state="normal")
        else:
            self.btn_bulk_migrate.configure(state="disabled")
            self.btn_bulk_data.configure(state="disabled")
            self.btn_select_all.configure(state="disabled")
    
    def toggle_select_all(self):
        """Tüm satırları seç veya seçimi kaldır"""
        all_items = self.tree.get_children()
        current_selection = self.tree.selection()
        
        if len(current_selection) == len(all_items):
            # Tümü seçili, seçimi kaldır
            self.tree.selection_remove(*all_items)
            self.btn_select_all.configure(text="☑ Tümünü Seç")
            self.log(f"Seçim kaldırıldı")
        else:
            # Tümünü seç
            self.tree.selection_set(all_items)
            self.btn_select_all.configure(text="☐ Seçimi Kaldır")
            self.log(f"{len(all_items)} tablo seçildi")
    
    def open_bulk_migration_dialog(self):
        """Seçili tüm tablolar için toplu işlem dialogu aç"""
        selected = self.tree.selection()
        
        if not selected:
            # Hiç seçili değilse tümünü seç
            selected = self.tree.get_children()
            if not selected:
                messagebox.showwarning("Uyarı", "İşlem yapılacak tablo yok.")
                return
        
        if not self.engine1 or not self.engine2:
            messagebox.showerror("Hata", "Her iki veritabanına da bağlantı gerekli.")
            return
        
        # Seçili tabloları topla
        tables = []
        for item_id in selected:
            item = self.tree.item(item_id)
            values = item['values']
            schema = values[0] if values[0] and values[0] != 'default' else None
            table_name = values[1]
            tables.append({'schema': schema, 'table_name': table_name})
        
        # Onay iste
        confirm = messagebox.askyesno(
            "⚠️ TOPLU İŞLEM",
            f"{len(tables)} tablo seçildi.\n\n"
            f"Bu tablolar için DROP CASCADE ve CREATE TABLE scriptleri üretilecek.\n\n"
            f"Devam etmek istiyor musunuz?",
            icon="warning"
        )
        
        if not confirm:
            return
        
        # Toplu script üretimi popup'ı
        BulkMigrationDialog(
            self,
            tables=tables,
            source_engine=self.engine1,
            target_engine=self.engine2,
            source_name=self.db1_name,
            target_name=self.db2_name
        )
        
        self.log(f"Toplu işlem başlatıldı: {len(tables)} tablo")
    
    def open_bulk_data_transfer(self):
        """Seçili tüm tabloların verilerini paralel aktar"""
        selected = self.tree.selection()
        
        if not selected:
            selected = self.tree.get_children()
            if not selected:
                messagebox.showwarning("Uyarı", "Aktarılacak tablo yok.")
                return
        
        if not self.engine1 or not self.engine2:
            messagebox.showerror("Hata", "Her iki veritabanına da bağlantı gerekli.")
            return
        
        # Seçili tabloları topla
        tables = []
        for item_id in selected:
            item = self.tree.item(item_id)
            values = item['values']
            schema = values[0] if values[0] and values[0] != 'default' else None
            table_name = values[1]
            tables.append({'schema': schema, 'table_name': table_name})
        
        # Onay iste
        confirm = messagebox.askyesno(
            "📤 TOPLU VERİ AKTARIMI",
            f"{len(tables)} tablonun verileri\n"
            f"{self.db1_name} → {self.db2_name}\n\n"
            f"aktarılacak. Bu işlem paralel çalışacak ve hızlı olacak.\n\n"
            f"Devam etmek istiyor musunuz?",
            icon="question"
        )
        
        if not confirm:
            return
        
        # Veri aktarım popup'ı
        BulkDataTransferDialog(
            self,
            tables=tables,
            source_engine=self.engine1,
            target_engine=self.engine2,
            source_name=self.db1_name,
            target_name=self.db2_name
        )
        
        self.log(f"Toplu veri aktarımı başlatıldı: {len(tables)} tablo")

    
    def on_tree_right_click(self, event):
        """Sağ tık context menüsü"""
        # Tıklanan satırı seç
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            
            # Context menu oluştur (tkinter.Menu kullan)
            import tkinter as tk
            
            if self.context_menu:
                self.context_menu.destroy()
            
            self.context_menu = tk.Menu(self, tearoff=0)
            
            # Menü öğeleri
            if self.current_view == "comparison":
                self.context_menu.add_command(
                    label="📊 Veri Farkını Göster",
                    command=lambda: self.on_tree_double_click(None)
                )
            
            if self.engine1 and self.engine2:
                self.context_menu.add_command(
                    label="📦 Yapıyı Aktar (DB1 → DB2)",
                    command=lambda: self.open_migration_dialog(direction="db1_to_db2")
                )
                self.context_menu.add_command(
                    label="📦 Yapıyı Aktar (DB2 → DB1)",
                    command=lambda: self.open_migration_dialog(direction="db2_to_db1")
                )
            
            self.context_menu.add_separator()
            self.context_menu.add_command(label="İptal", command=lambda: None)
            
            # Menüyü göster
            self.context_menu.tk_popup(event.x_root, event.y_root)
    
    def open_migration_dialog(self, direction=None):
        """Tablo yapısı migrasyon dialogunu aç"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Uyarı", "Lütfen bir tablo seçin.")
            return
        
        if not self.engine1 or not self.engine2:
            messagebox.showerror("Hata", "Her iki veritabanına da bağlantı gerekli.")
            return
        
        # Seçili tabloyu al
        item = self.tree.item(selected[0])
        values = item['values']
        schema = values[0] if values[0] and values[0] != 'default' else None
        table_name = values[1]
        
        # Varsayılan yön: DB1 → DB2
        if direction == "db2_to_db1":
            source_engine = self.engine2
            target_engine = self.engine1
            source_name = self.db2_name
            target_name = self.db1_name
        else:
            source_engine = self.engine1
            target_engine = self.engine2
            source_name = self.db1_name
            target_name = self.db2_name
        
        # Dialog aç
        TableMigrationDialog(
            self,
            schema=schema,
            table_name=table_name,
            source_engine=source_engine,
            target_engine=target_engine,
            source_name=source_name,
            target_name=target_name
        )
        
        self.log(f"Yapı aktarımı: {schema}.{table_name} ({source_name} → {target_name})")


    def toggle_view(self):
        """Tablo listesi ve karşılaştırma sonuçları arasında geçiş yapar"""
        if self.current_view == "discovery":
            # Sonuçları göster
            if self.comparison_results:
                self.current_view = "comparison"
                self.populate_comparison_tree(self.comparison_results)
                self.btn_toggle_view.configure(text="Tablo Listesi")
                self.btn_add_table.configure(state="disabled")
                self.btn_remove_table.configure(state="disabled")
                self.table_header.configure(text=f"Karşılaştırma Sonuçları ({len(self.comparison_results)})")
                self.log("Görünüm: Karşılaştırma sonuçları")
        else:
            # Tablo listesine dön
            self.current_view = "discovery"
            self.populate_discovery_tree()
            self.btn_toggle_view.configure(text="Sonuçları Göster")
            self.btn_add_table.configure(state="normal")
            self.table_header.configure(text=f"Bulunan Tanım Tabloları ({len(self.selected_tables)})")
            self.log("Görünüm: Tablo listesi")

    # ========== ADIM 1: TABLO KEŞFİ ==========
    def start_discovery_thread(self):
        self.btn_scan.configure(state="disabled")
        self.btn_compare.configure(state="disabled")
        self.progressbar.start()
        self.update_status("Taranıyor...", "Veritabanları taranıyor", COLORS["warning"])
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.selected_tables = {}
        self.manual_tables = []
        
        thread = threading.Thread(target=self.run_discovery)
        thread.start()

    def run_discovery(self):
        try:
            self.db1_name = self.entry_db1_name.get() or "DB1"
            self.db2_name = self.entry_db2_name.get() or "DB2"
            
            db1_is_file = self.db1_source_var.get() == "file"
            db2_is_file = self.db2_source_var.get() == "file"
            
            self.log(f"\n--- TABLO KEŞFİ ---")
            self.log(f"Kaynak 1: {self.db1_name} ({'Dosya' if db1_is_file else 'DB'})")
            self.log(f"Kaynak 2: {self.db2_name} ({'Dosya' if db2_is_file else 'DB'})")
            
            # DB1 verilerini al
            if db1_is_file:
                if not self.db1_snapshot_path:
                    self.log("HATA: DB1 için snapshot seçilmedi")
                    self.after(0, lambda: self.finish_discovery(success=False))
                    return
                self.log(f"{self.db1_name} dosyadan yükleniyor...")
                success, self.db1_data, meta1, msg = logic.load_snapshot(self.db1_snapshot_path)
                if not success:
                    self.log(f"HATA: {msg}")
                    self.after(0, lambda: self.finish_discovery(success=False))
                    return
                cand1 = [{"schema": v["schema"], "table_name": v["table_name"], "full_name": k} for k, v in self.db1_data.items()]
                self.log(f"  {len(cand1)} tablo yüklendi")
                self.engine1 = None
            else:
                db1_url = self.entry_db1_url.get()
                self.log(f"{self.db1_name} veritabanına bağlanılıyor...")
                self.engine1 = logic.get_db_engine(db1_url)
                if not self.engine1:
                    self.log("HATA: DB1 bağlantısı başarısız.")
                    self.after(0, lambda: self.finish_discovery(success=False))
                    return
                cand1, rej1 = logic.find_definition_tables(self.engine1)
                self.log(f"  {len(cand1)} tanım tablosu bulundu")
                self.db1_data = None
            
            # DB2 verilerini al
            if db2_is_file:
                if not self.db2_snapshot_path:
                    self.log("HATA: DB2 için snapshot seçilmedi")
                    self.after(0, lambda: self.finish_discovery(success=False))
                    return
                self.log(f"{self.db2_name} dosyadan yükleniyor...")
                success, self.db2_data, meta2, msg = logic.load_snapshot(self.db2_snapshot_path)
                if not success:
                    self.log(f"HATA: {msg}")
                    self.after(0, lambda: self.finish_discovery(success=False))
                    return
                cand2 = [{"schema": v["schema"], "table_name": v["table_name"], "full_name": k} for k, v in self.db2_data.items()]
                self.log(f"  {len(cand2)} tablo yüklendi")
                self.engine2 = None
            else:
                db2_url = self.entry_db2_url.get()
                self.log(f"{self.db2_name} veritabanına bağlanılıyor...")
                self.engine2 = logic.get_db_engine(db2_url)
                if not self.engine2:
                    self.log("HATA: DB2 bağlantısı başarısız.")
                    self.after(0, lambda: self.finish_discovery(success=False))
                    return
                cand2, rej2 = logic.find_definition_tables(self.engine2)
                self.log(f"  {len(cand2)} tanım tablosu bulundu")
                self.db2_data = None

            map1 = {t['full_name']: t for t in cand1}
            map2 = {t['full_name']: t for t in cand2}

            # Ortak tablolar
            common_names = list(set(map1.keys()) & set(map2.keys()))
            only_db1 = list(set(map1.keys()) - set(map2.keys()))
            only_db2 = list(set(map2.keys()) - set(map1.keys()))
            
            self.log(f"\nSonuç: {len(common_names)} ortak, {len(only_db1)} sadece {self.db1_name}, {len(only_db2)} sadece {self.db2_name}")
            
            # Tabloları listeye ekle
            for fn in common_names:
                t = map1[fn]
                t['status'] = 'Ortak'
                t['source'] = 'Otomatik'
                self.selected_tables[fn] = t
            
            # Otomatik snapshot kaydet (her taramada güncelle)
            if not db1_is_file and self.engine1 and len(self.selected_tables) > 0:
                self.log(f"\n{self.db1_name} snapshot güncelleniyor...")
                table_list = list(self.selected_tables.values())
                success, path, msg = logic.export_db_to_snapshot(self.engine1, self.db1_name, table_list, overwrite=True)
                self.log(f"  Snapshot: {msg}")
            
            if not db2_is_file and self.engine2 and len(self.selected_tables) > 0:
                self.log(f"{self.db2_name} snapshot güncelleniyor...")
                table_list = list(self.selected_tables.values())
                success, path, msg = logic.export_db_to_snapshot(self.engine2, self.db2_name, table_list, overwrite=True)
                self.log(f"  Snapshot: {msg}")
            
            self.after(0, lambda: self.populate_discovery_tree())
            self.after(0, lambda: self.finish_discovery(success=True))

        except Exception as e:
            self.log(f"HATA: {e}")
            import traceback
            traceback.print_exc()
            self.after(0, lambda: self.finish_discovery(success=False))

    def populate_discovery_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Tablo kolonlarını güncelle (keşif modu)
        self.tree.heading("Durum", text="Durum")
        
        for fn, t in sorted(self.selected_tables.items()):
            source = t.get('source', 'Otomatik')
            tag = "manual" if source == "Manuel" else "auto"
            self.tree.insert("", "end", values=(t['schema'], t['table_name'], source, t['status']), tags=(tag,))
        
        self.tree.tag_configure("manual", foreground=COLORS["success"])
        self.tree.tag_configure("auto", foreground=COLORS["text_primary"])

    def finish_discovery(self, success):
        self.progressbar.stop()
        self.btn_scan.configure(state="normal")
        
        if success:
            self.progressbar.set(1)
            count = len(self.selected_tables)
            schemas = set(t['schema'] for t in self.selected_tables.values())
            
            self.update_status("Tarama Tamamlandı", f"{len(schemas)} şema, {count} tablo bulundu", COLORS["success"])
            self.table_header.configure(text=f"Bulunan Tanım Tabloları ({count})")
            
            # İstatistik kartları
            for card in self.stat_cards:
                card.destroy()
            self.stat_cards = []
            
            stats = [
                ("Toplam Tablo", str(count), COLORS["accent"]),
                ("Şema", str(len(schemas)), COLORS["text_primary"]),
                ("Manuel", "0", COLORS["success"]),
            ]
            
            for label, value, color in stats:
                card = ctk.CTkFrame(self.stats_frame, fg_color=COLORS["bg_card"], corner_radius=8)
                card.pack(side="left", padx=5)
                ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack(padx=12, pady=(6, 1))
                ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=9), text_color=COLORS["text_muted"]).pack(padx=12, pady=(0, 6))
                self.stat_cards.append(card)
            
            # Butonları aktif et
            self.btn_compare.configure(state="normal", fg_color=COLORS["accent"], 
                hover_color=COLORS["accent_hover"], text_color=COLORS["bg_primary"])
            self.btn_add_table.configure(state="normal")
            self.current_phase = "discovery"
            
            self.log(f"\nTablo listesi hazır. İsterseniz manuel tablo ekleyebilir veya silebilirsiniz.")
            self.log("Hazır olduğunuzda 'Karşılaştır' butonuna tıklayın.")
        else:
            self.progressbar.set(0)
            self.update_status("Hata", "Tarama başarısız", COLORS["error"])

    def add_manual_table(self):
        dialog = AddTableDialog(self)
        self.wait_window(dialog)
        
        if dialog.result:
            t = dialog.result
            fn = t['full_name']
            
            if fn in self.selected_tables:
                messagebox.showwarning("Uyarı", f"'{fn}' zaten listede mevcut.")
                return
            
            t['status'] = 'Manuel Eklendi'
            t['source'] = 'Manuel'
            self.selected_tables[fn] = t
            self.manual_tables.append(t)
            
            self.populate_discovery_tree()
            self.update_table_stats()
            self.log(f"Manuel tablo eklendi: {fn}")

    def remove_selected_table(self):
        selected = self.tree.selection()
        if not selected:
            return
        
        for item in selected:
            values = self.tree.item(item)['values']
            fn = f"{values[0]}.{values[1]}" if values[0] else values[1]
            
            if fn in self.selected_tables:
                del self.selected_tables[fn]
                self.manual_tables = [t for t in self.manual_tables if t['full_name'] != fn]
                self.log(f"Tablo silindi: {fn}")
        
        self.populate_discovery_tree()
        self.update_table_stats()

    def update_table_stats(self):
        count = len(self.selected_tables)
        schemas = set(t['schema'] for t in self.selected_tables.values())
        manual_count = len(self.manual_tables)
        
        self.table_header.configure(text=f"Bulunan Tanım Tabloları ({count})")
        
        # Stat kartlarını güncelle
        if len(self.stat_cards) >= 3:
            self.stat_cards[0].winfo_children()[0].configure(text=str(count))
            self.stat_cards[1].winfo_children()[0].configure(text=str(len(schemas)))
            self.stat_cards[2].winfo_children()[0].configure(text=str(manual_count))

    # ========== ADIM 2: KARŞILAŞTIRMA ==========
    def start_comparison_thread(self):
        db1_is_file = self.db1_source_var.get() == "file"
        db2_is_file = self.db2_source_var.get() == "file"
        
        # Dosya-dosya modunda taramaya gerek yok
        if db1_is_file and db2_is_file:
            if not self.db1_snapshot_path or not self.db2_snapshot_path:
                messagebox.showwarning("Uyarı", "Lütfen her iki kaynak için de snapshot seçin.")
                return
        elif not self.selected_tables:
            messagebox.showwarning("Uyarı", "Karşılaştırılacak tablo yok. Önce tabloları tarayın.")
            return
        
        self.btn_scan.configure(state="disabled")
        self.btn_compare.configure(state="disabled")
        self.btn_add_table.configure(state="disabled")
        self.btn_remove_table.configure(state="disabled")
        self.progressbar.start()
        self.update_status("Karşılaştırılıyor...", "Tablolar karşılaştırılıyor", COLORS["warning"])
        
        self.current_phase = "comparison"
        thread = threading.Thread(target=self.run_comparison)
        thread.start()

    def run_comparison(self):
        try:
            mode = self._selected_mode
            manual_count = len(self.manual_tables)
            
            db1_is_file = self.db1_source_var.get() == "file"
            db2_is_file = self.db2_source_var.get() == "file"
            
            self.db1_name = self.entry_db1_name.get() or "DB1"
            self.db2_name = self.entry_db2_name.get() or "DB2"

            self.log(f"\n--- KARŞILAŞTIRMA ---")
            self.log(f"Mod: {mode}")
            
            # Dosya-dosya modunda snapshot'lardan veri yükle
            if db1_is_file and db2_is_file:
                self.log("Kaynak: Dosya ↔ Dosya")
                
                # DB1 snapshot yükle
                success, self.db1_data, meta1, msg = logic.load_snapshot(self.db1_snapshot_path)
                if not success:
                    self.log(f"HATA: {msg}")
                    self.after(0, lambda: self.finish_comparison(False, 0))
                    return
                self.log(f"  {self.db1_name}: {len(self.db1_data)} tablo yüklendi")
                
                # DB2 snapshot yükle
                success, self.db2_data, meta2, msg = logic.load_snapshot(self.db2_snapshot_path)
                if not success:
                    self.log(f"HATA: {msg}")
                    self.after(0, lambda: self.finish_comparison(False, 0))
                    return
                self.log(f"  {self.db2_name}: {len(self.db2_data)} tablo yüklendi")
                
                # Ortak tabloları bul ve karşılaştır
                common_tables = set(self.db1_data.keys()) & set(self.db2_data.keys())
                self.log(f"  Ortak tablo sayısı: {len(common_tables)}")
                
                # Dosya-dosya karşılaştırma
                results = logic.compare_tables_from_data(
                    self.db1_data, self.db2_data, 
                    self.db1_name, self.db2_name, 
                    base_db=mode
                )
                self.comparison_results = results
                
            elif db1_is_file or db2_is_file:
                # Karışık mod: DB ↔ Dosya
                self.log(f"Kaynak: {'Dosya' if db1_is_file else 'DB'} ↔ {'Dosya' if db2_is_file else 'DB'}")
                
                # Dosya kaynağını yükle
                if db1_is_file:
                    success, self.db1_data, meta1, msg = logic.load_snapshot(self.db1_snapshot_path)
                    if not success:
                        self.log(f"HATA: {msg}")
                        self.after(0, lambda: self.finish_comparison(False, 0))
                        return
                    self.log(f"  {self.db1_name} (Dosya): {len(self.db1_data)} tablo")
                    
                if db2_is_file:
                    success, self.db2_data, meta2, msg = logic.load_snapshot(self.db2_snapshot_path)
                    if not success:
                        self.log(f"HATA: {msg}")
                        self.after(0, lambda: self.finish_comparison(False, 0))
                        return
                    self.log(f"  {self.db2_name} (Dosya): {len(self.db2_data)} tablo")
                
                # Karşılaştırılacak tabloları belirle
                table_list = list(self.selected_tables.values())
                self.log(f"  Karşılaştırılacak tablo: {len(table_list)}")
                
                # Karışık karşılaştırma
                results = logic.compare_tables_mixed(
                    db_engine=self.engine2 if db1_is_file else self.engine1,
                    file_data=self.db1_data if db1_is_file else self.db2_data,
                    table_list=table_list,
                    db_name=self.db2_name if db1_is_file else self.db1_name,
                    file_name=self.db1_name if db1_is_file else self.db2_name,
                    db_is_target=(not db1_is_file),  # DB birinci ise DB hedef
                    base_db=mode
                )
                self.comparison_results = results
                
            else:
                # Normal DB ↔ DB karşılaştırma
                self.log(f"Toplam tablo: {len(self.selected_tables)} (Manuel: {manual_count})")
                table_list = list(self.selected_tables.values())
                
                self.log(f"\nKarşılaştırılıyor...")
                results = logic.compare_tables(self.engine1, self.engine2, table_list, 
                    self.db1_name, self.db2_name, base_db=mode)
                self.comparison_results = results
            
            # Tablo görünümünü karşılaştırma sonuçlarıyla güncelle
            self.after(0, lambda: self.populate_comparison_tree(results))
            
            # Excel kaydet
            success, msg = logic.save_to_excel(results, self.db1_name, self.db2_name, mode)
            self.log(f"Rapor: {msg}")

            self.after(0, lambda: self.finish_comparison(success=success, manual_count=manual_count))

        except Exception as e:
            self.log(f"HATA: {e}")
            self.after(0, lambda: self.finish_comparison(success=False, manual_count=0))

    def populate_comparison_tree(self, results):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Kolon başlıklarını ve genişliklerini güncelle (karşılaştırma modu)
        self.tree.heading("Kaynak", text="Fark")
        self.tree.heading("Durum", text="Açıklama")
        self.tree.column("Şema", width=150)
        self.tree.column("Tablo", width=200)
        self.tree.column("Kaynak", width=60)
        self.tree.column("Durum", width=400)  # Açıklama için geniş
        
        for res in results:
            durum = res.get('Durum', '')
            tag = "equal" if durum == "EŞİT" else "different"
            
            # Manuel mi kontrol et
            fn = f"{res.get('Şema', '')}.{res.get('Tablo', '')}"
            is_manual = fn in [t['full_name'] for t in self.manual_tables]
            if is_manual:
                tag = "manual_" + tag
            
            self.tree.insert("", "end", values=(
                res.get('Şema', ''),
                res.get('Tablo', ''),
                res.get('Fark (Adet)', 0),
                res.get('Açıklama', '')
            ), tags=(tag,))
        
        self.tree.tag_configure("equal", foreground=COLORS["success"])
        self.tree.tag_configure("different", foreground=COLORS["warning"])
        self.tree.tag_configure("manual_equal", foreground=COLORS["success"])
        self.tree.tag_configure("manual_different", foreground=COLORS["warning"])
        
        self.table_header.configure(text="Karşılaştırma Sonuçları")

    def finish_comparison(self, success, manual_count):
        self.progressbar.stop()
        self.btn_scan.configure(state="normal")
        self.btn_compare.configure(state="normal")
        
        if success:
            self.progressbar.set(1)
            
            equal_count = sum(1 for r in self.comparison_results if r.get('Durum') == 'EŞİT')
            diff_count = sum(1 for r in self.comparison_results if r.get('Durum') == 'FARKLI')
            error_count = sum(1 for r in self.comparison_results if r.get('Durum') == 'HATA')
            total_count = len(self.comparison_results)
            schemas = set(r.get('Şema', 'default') for r in self.comparison_results)
            total_diff_records = sum(r.get('Fark (Adet)', 0) for r in self.comparison_results)
            
            self.lbl_status.configure(text="Tamamlandı", text_color=COLORS["success"])
            self.lbl_status_desc.configure(text=f"{len(schemas)} şema, {total_count} tablo ({manual_count} manuel)")
            
            # Stat kartları
            for card in self.stat_cards:
                card.destroy()
            self.stat_cards = []
            
            stats = [
                ("Eşit", str(equal_count), COLORS["success"]),
                ("Farklı", str(diff_count), COLORS["warning"]),
                ("Toplam Fark", str(total_diff_records), COLORS["accent"]),
                ("Manuel", str(manual_count), COLORS["success"]),
            ]
            if error_count > 0:
                stats.append(("Hata", str(error_count), COLORS["error"]))
            
            for label, value, color in stats:
                card = ctk.CTkFrame(self.stats_frame, fg_color=COLORS["bg_card"], corner_radius=8)
                card.pack(side="left", padx=5)
                ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack(padx=12, pady=(6, 1))
                ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=9), text_color=COLORS["text_muted"]).pack(padx=12, pady=(0, 6))
                self.stat_cards.append(card)
            
            self.btn_open_report.configure(state="normal", fg_color=COLORS["success"], hover_color="#66bb6a")
            self.btn_toggle_view.configure(state="normal", text="Tablo Listesi")
            self.current_view = "comparison"
            self.log(f"\nKarşılaştırma tamamlandı: {equal_count} eşit, {diff_count} farklı, {total_diff_records} toplam fark kaydı")
            if manual_count > 0:
                self.log(f"  (Manuel eklenen {manual_count} tablo dahil)")
            self.log("Tablo listesine dönmek için 'Tablo Listesi' butonuna tıklayın.")
        else:
            self.progressbar.set(0)
            self.update_status("Hata", "Karşılaştırma başarısız", COLORS["error"])

    def on_tree_double_click(self, event):
        if self.current_view != "comparison":
            return
            
        selected_item = self.tree.selection()
        if not selected_item:
            return
            
        item = self.tree.item(selected_item[0])
        values = item['values']
        
        schema = values[0] if values[0] != 'default' else None
        table_name = values[1]
        
        # Sonuçlardan durumu bul
        fn = f"{schema}.{table_name}" if schema else table_name
        result = next((r for r in self.comparison_results if f"{r.get('Şema')}.{r.get('Tablo')}" == fn), None)
        
        if result and result.get('Durum') == "EŞİT":
            messagebox.showinfo("Bilgi", f"'{table_name}' tablosu her iki veritabanında da aynı.")
            return
        
        if not self.engine1 or not self.engine2:
            messagebox.showerror("Hata", "Veritabanı bağlantısı yok.")
            return
        
        self.log(f"SQL hesaplanıyor: {table_name}...")
        sql_db2, sql_db1, error = logic.get_table_diff_data(
            self.engine1, self.engine2, schema, table_name, self.db1_name, self.db2_name
        )
        
        if error:
            messagebox.showerror("Hata", f"SQL üretilemedi: {error}")
            return
        
        SQLPopup(self, fn, sql_db2, sql_db1, self.db1_name, self.db2_name, self.engine1, self.engine2)

    def open_report(self):
        file_path = "veri_farkliliklari.xlsx"
        if os.path.exists(file_path):
            if sys.platform == "win32":
                os.startfile(file_path)
            else:
                opener = "open" if sys.platform == "darwin" else "xdg-open"
                subprocess.call([opener, file_path])
        else:
            messagebox.showerror("Hata", "Rapor dosyası bulunamadı.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
