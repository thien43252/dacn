# Deploy EduAgent Hub lên Oracle Cloud (Always Free)

Kiến trúc: 1 VM chạy Docker Compose gồm `postgres` (pgvector), `backend` (FastAPI) và `web` (Caddy phục vụ
file tĩnh + proxy `/api` + tự cấp HTTPS). Cùng một origin nên không cần lo CORS/cookie.

## 1. Tạo VM (Oracle Console)
1. Compute > Instances > Create instance.
2. Image: **Ubuntu 22.04** (hoặc 24.04). Shape: **VM.Standard.A1.Flex** (ARM), 2 OCPU / 12GB RAM là đủ.
   Nếu báo "out of capacity" thì thử lại sau hoặc dùng shape `VM.Standard.E2.1.Micro` (chỉ 1GB, rất chật).
3. Networking: để mặc định (tạo VCN mới), bật **Assign public IPv4**.
4. Add SSH keys > Generate a key pair > tải **private key** về (đừng mất).
5. Boot volume: 50–100GB.
6. Tạo xong ghi lại **Public IP**.

## 2. Mở cổng 80/443 ở Oracle
Networking > Virtual Cloud Networks > VCN của bạn > Subnet > Security List > Add Ingress Rules:
- Source CIDR `0.0.0.0/0`, TCP, Destination port `80`
- Source CIDR `0.0.0.0/0`, TCP, Destination port `443`

## 3. SSH vào VM
```
ssh -i đường/dẫn/private.key ubuntu@<PUBLIC_IP>
```
(Windows: PowerShell, nếu báo "permissions too open" thì chuột phải file key > Properties > Security chỉ để lại tài khoản của bạn.)

## 4. Mở firewall trong máy + cài Docker (chạy trên VM)
```
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo apt-get install -y iptables-persistent
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
```

## 5. Lấy code
Repo private thì dùng deploy key hoặc personal access token. Ví dụ:
```
git clone https://github.com/<user>/<repo>.git eduagent && cd eduagent
```
Không dùng git: từ máy bạn `scp -i key -r` thư mục dự án (bỏ `node_modules`, `.venv`).

## 6. Tạo .env
```
cp infra/prod/.env.example .env
nano .env
```
Cần sửa:
- `POSTGRES_PASSWORD`: chuỗi dài ngẫu nhiên (`openssl rand -hex 24`).
- `SITE_ADDRESS`: nếu chưa có tên miền, dùng `<ip-thay-dấu-chấm-bằng-gạch>.sslip.io`, ví dụ IP `129.146.10.20`
  -> `129-146-10-20.sslip.io`. Có tên miền thì trỏ A record về IP rồi điền tên miền (không có `https://`).
- `LLM_PROVIDER`, tên model và API key tương ứng. Muốn chạy thử không tốn tiền: `LLM_PROVIDER=fake`,
  `EMBEDDING_PROVIDER=fake`.
- `SEED_DEMO=1` tạo tài khoản demo (mật khẩu cố định trong `scripts/seed_demo.py`). Sau khi demo xong nên tắt hoặc đổi.

## 7. Chạy
```
cd infra/prod
docker compose --env-file ../../.env up -d --build
docker compose --env-file ../../.env logs -f backend
```
Lần build đầu mất vài phút. Mở `https://<SITE_ADDRESS>`. Kiểm tra: `curl https://<SITE_ADDRESS>/api/health/ready`.

## 8. Cập nhật phiên bản mới
```
cd ~/eduagent && git pull
cd infra/prod && docker compose --env-file ../../.env up -d --build
```
Migration chạy tự động khi backend khởi động.

## 9. Backup (nên làm)
```
cd ~/eduagent/infra/prod
docker compose --env-file ../../.env exec -T postgres pg_dump -U eduagent eduagent | gzip > ~/backup-$(date +%F).sql.gz
docker run --rm -v eduagent-prod_uploads:/d -v ~:/b alpine tar czf /b/uploads-$(date +%F).tgz -C /d .
```
Tải về máy bằng `scp`. Có thể đặt vào cron hằng ngày.

## Sự cố thường gặp
- Không vào được từ ngoài: thiếu rule ở bước 2 hoặc iptables ở bước 4 (phải có cả hai).
- Caddy không cấp được chứng chỉ: cổng 80/443 chưa mở, hoặc `SITE_ADDRESS` sai/chưa trỏ đúng IP.
- Đăng nhập xong bị văng: truy cập bằng `http://` thay vì `https://` (cookie Secure).
- Xem log: `docker compose --env-file ../../.env logs -f <backend|web|postgres>`.
