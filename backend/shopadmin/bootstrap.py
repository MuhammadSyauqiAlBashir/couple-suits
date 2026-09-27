"""First-run defaults: size charts, family-set discounts, help pages.
Runs at startup; each part only once (kv `bootstrap`). Everything is editable in the CMS."""

from __future__ import annotations

import logging

from cs import catalog
from cs.pb import pb

log = logging.getLogger("shopadmin.bootstrap")

PAGES = [
    {
        "slug": "cara-pesan", "sort": 1, "in_footer": True,
        "title_id": "Cara pesan", "title_en": "How to order",
        "body_id": """## 1. Susun set keluargamu
Di halaman produk, pilih **Susun set keluarga**: tambahkan setiap anggota (ayah, ibu, anak, dan lainnya) dan pilih ukuran masing-masing. Satu potong juga bisa.

## 2. Buat pesanan
Isi nama, nomor WhatsApp, dan alamat. Belum perlu bayar.

## 3. Konfirmasi via WhatsApp
Kami menghubungi kamu untuk konfirmasi ongkos kirim dan cara pembayaran (transfer bank / e-wallet).

## 4. Diproses & dikirim
Ready stock dikirim 1–2 hari kerja setelah pembayaran. Pre-order dibuat sesuai estimasi di halaman produk.

Pantau status pesanan lewat tautan yang kamu dapat setelah memesan, atau di menu **Akun**.""",
        "body_en": """## 1. Build your family set
On a product page, use **Build your family set**: add each person (dad, mum, kids and more) and pick their size. A single piece is fine too.

## 2. Place the order
Enter your name, WhatsApp number and address. No payment yet.

## 3. Confirm on WhatsApp
We message you to confirm the shipping cost and how to pay (bank transfer / e-wallet).

## 4. Made & shipped
In-stock items ship 1–2 working days after payment. Pre-orders are made within the time shown on the product page.

Track your order with the link you get after ordering, or under **Account**.""",
    },
    {
        "slug": "faq", "sort": 2, "in_footer": True, "title_id": "Pertanyaan umum", "title_en": "FAQ",
        "body_id": """### Apakah bisa beli satu potong saja?
Bisa. Pilih **Satu potong** di halaman produk.

### Bagaimana memilih ukuran anak?
Ukuran anak berdasarkan usia dan tinggi badan. Lihat **Panduan ukuran**, atau kirim tinggi & berat badan anak via WhatsApp — kami bantu pilihkan.

### Berapa lama pre-order?
Estimasi ada di halaman produk (biasanya 14–21 hari setelah pembayaran).

### Bisa tukar ukuran?
Bisa untuk barang ready stock yang belum dipakai, dengan label lengkap, maks. 7 hari setelah diterima. Lihat **Pengembalian & penukaran**.

### Pembayarannya bagaimana?
Setelah pesanan dibuat, kami kirim total + ongkir dan nomor rekening via WhatsApp.""",
        "body_en": """### Can I buy a single piece?
Yes. Choose **Single piece** on the product page.

### How do I choose kids' sizes?
Kids' sizes go by age and height. See the **Size guide**, or send us your child's height and weight on WhatsApp and we'll help.

### How long do pre-orders take?
The estimate is on the product page (usually 14–21 days after payment).

### Can I exchange a size?
Yes for unworn in-stock items with tags, within 7 days of delivery. See **Returns & exchanges**.

### How do I pay?
After you order, we send the total with shipping and our bank details on WhatsApp.""",
    },
    {
        "slug": "pengembalian", "sort": 3, "in_footer": True,
        "title_id": "Pengembalian & penukaran", "title_en": "Returns & exchanges",
        "body_id": """- Penukaran ukuran untuk barang **ready stock**: maks. **7 hari** setelah barang diterima, belum dipakai/dicuci, label masih terpasang.
- Barang **pre-order** dibuat khusus sesuai ukuran pesanan sehingga tidak bisa ditukar, kecuali ada cacat produksi.
- Jika barang cacat atau salah kirim, kami ganti tanpa biaya. Kirim foto/video unboxing via WhatsApp.
- Ongkos kirim penukaran (bukan karena kesalahan kami) ditanggung pembeli.""",
        "body_en": """- Size exchanges for **in-stock** items: within **7 days** of delivery, unworn/unwashed, tags attached.
- **Pre-order** items are made to your sizes and can't be exchanged unless there's a defect.
- Defective or wrong items are replaced free. Send an unboxing photo/video on WhatsApp.
- Shipping for exchanges that aren't our mistake is paid by the customer.""",
    },
    {
        "slug": "privacy", "sort": 9, "in_footer": True, "title_id": "Kebijakan privasi", "title_en": "Privacy policy",
        "body_id": """*Terakhir diperbarui: 27 September 2026. (Draf — mohon ditinjau pemilik toko.)*

Kami menghormati privasimu dan mengelola data pribadi sesuai **UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP)**.

## Data yang kami kumpulkan
- **Saat memesan:** nama, nomor WhatsApp, email (opsional), alamat pengiriman, catatan pesanan.
- **Jika membuat akun:** email, kata sandi (disimpan terenkripsi), nama, dan — jika kamu isi — profil ukuran keluarga, tanggal lahir/anniversary.
- **Ulasan:** nama tampil, isi ulasan, dan foto yang kamu unggah dengan persetujuan.
- **Statistik kunjungan:** jumlah kunjungan dan halaman yang dilihat secara agregat. Kami **tidak** memakai cookie pelacak atau iklan; alamat IP tidak disimpan.

## Untuk apa data dipakai
Memproses dan mengirim pesanan, menghubungi kamu via WhatsApp tentang pesanan, menyimpan ukuran keluarga agar belanja lebih mudah, dan — jika kamu setuju — mengirim info koleksi atau voucher spesial.

## Berbagi data
Data hanya dibagikan ke jasa pengiriman sebatas yang diperlukan untuk mengantar paket. Kami tidak menjual data pribadi.

## Penyimpanan & keamanan
Data disimpan di server kami di Indonesia dengan akses terbatas dan koneksi terenkripsi (HTTPS).

## Hak kamu
Kamu berhak mengakses, memperbaiki, dan meminta penghapusan data pribadimu, serta menarik persetujuan pemasaran kapan saja. Hubungi kami via WhatsApp atau email yang tercantum di situs.""",
        "body_en": """*Last updated: 27 September 2026. (Draft — to be reviewed by the shop owner.)*

We respect your privacy and handle personal data under Indonesia's **Personal Data Protection Law (UU PDP, Law No. 27 of 2022)**.

## What we collect
- **When you order:** name, WhatsApp number, email (optional), delivery address, order notes.
- **If you create an account:** email, password (stored encrypted), name and — if you add them — family size profiles, birthday/anniversary.
- **Reviews:** display name, review text and photos you upload with consent.
- **Visit statistics:** aggregate counts of visits and pages viewed. We use **no** tracking or advertising cookies; IP addresses are not stored.

## How we use it
To process and deliver orders, contact you on WhatsApp about your order, remember family sizes to make shopping easier, and — if you agree — send news or special vouchers.

## Sharing
Only with delivery couriers, as needed to deliver your parcel. We never sell personal data.

## Storage & security
Data is stored on our server in Indonesia with restricted access and encrypted connections (HTTPS).

## Your rights
You can access, correct or ask us to delete your personal data, and withdraw marketing consent at any time. Contact us on WhatsApp or by the email on this site.""",
    },
    {
        "slug": "tentang-kami", "sort": 0, "in_footer": True, "status": "draft", "title_id": "Tentang kami", "title_en": "About us",
        "body_id": "Tulis cerita brand di sini.", "body_en": "Write the brand story here.",
    },
]


async def run():
    done = await pb.kv_get("bootstrap", {}) or {}
    changed = False
    if not done.get("charts"):
        existing = {c["name"] for c in await pb.all("shop_size_charts", fields="name")}
        for chart in catalog.DEFAULT_CHARTS:
            if chart["name"] not in existing:
                await pb.create("shop_size_charts", chart)
        done["charts"] = changed = True
    if not done.get("set_discounts"):
        if not await pb.all("shop_set_discounts", fields="id"):
            await pb.create("shop_set_discounts", {"min_members": 3, "percent": 5, "label_id": "Diskon set keluarga 5%",
                                                   "label_en": "Family set 5% off", "active": True})
            await pb.create("shop_set_discounts", {"min_members": 5, "percent": 10, "label_id": "Diskon set keluarga 10%",
                                                   "label_en": "Family set 10% off", "active": True})
        done["set_discounts"] = changed = True
    if not done.get("pages"):
        for p in PAGES:
            if not await pb.first("shop_pages", f"slug = '{p['slug']}'"):
                await pb.create("shop_pages", {"status": "live", **p})
        done["pages"] = changed = True
    if changed:
        await pb.kv_set("bootstrap", done)
        log.info("first-run defaults created: %s", ", ".join(k for k, v in done.items() if v))
