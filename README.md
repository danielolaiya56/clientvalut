# ClientVault — 3-Tier App Deployment Guide
**Stack: Flask (Python) + MySQL RDS + AWS S3 + EC2**

---

## Project Structure
```
clientvault/
├── app.py               ← Flask backend (API + DB logic)
├── requirements.txt     ← Python packages
├── gunicorn.conf.py     ← Production server config
├── .env.example         ← Copy this to .env and fill in values
├── .gitignore           ← Keeps .env off GitHub
└── templates/
    └── index.html       ← Frontend (served by Flask)
```

---

## STEP 1 — Push to GitHub

Run these commands on your local machine:

```bash
# Navigate into your project folder
cd clientvault

# Initialize git
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - ClientVault 3-tier app"

# Create a new repo on GitHub.com, then connect it:
git remote add origin https://github.com/YOUR_USERNAME/clientvault.git

# Push
git push -u origin main
```

> ⚠️ Make sure .env is in .gitignore — NEVER push your credentials to GitHub!

---

## STEP 2 — Configure AWS S3 Bucket

1. Go to **AWS Console → S3 → Your Bucket → Permissions**

2. **Disable "Block all public access"** (uncheck all boxes, save)

3. Add this **CORS policy** (Permissions tab → CORS):
```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": []
  }
]
```

4. Add this **Bucket Policy** (replace YOUR-BUCKET-NAME):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
    }
  ]
}
```

5. Create an **IAM User** for the app:
   - AWS Console → IAM → Users → Create User
   - Attach policy: **AmazonS3FullAccess**
   - Create Access Key → Save the Key ID and Secret ← you'll need these for .env

---

## STEP 3 — Set Up MySQL RDS

1. **AWS Console → RDS → Create Database**
   - Engine: MySQL
   - Template: Free tier
   - DB identifier: `clientvault-db`
   - Master username: `admin`
   - Master password: (choose a strong password, save it)

2. **Connectivity settings:**
   - Public access: YES (for now, to allow EC2 to reach it)
   - VPC Security Group: make sure port **3306** is open to your EC2's IP

3. After creation, copy the **Endpoint** (looks like `clientvault-db.xxxx.us-east-1.rds.amazonaws.com`)

4. Connect to RDS and create the database:
```bash
# From your EC2 or local machine
mysql -h YOUR-RDS-ENDPOINT -u admin -p

# In MySQL shell:
CREATE DATABASE clientvault;
EXIT;
```

> Flask/SQLAlchemy will create the tables automatically when you start the app.

---

## STEP 4 — Set Up Your EC2 Instance

SSH into your EC2 instance:
```bash
ssh -i your-key.pem ec2-user@YOUR-EC2-PUBLIC-IP
```

### Install dependencies:
```bash
# Update system
sudo yum update -y        # Amazon Linux
# OR
sudo apt update -y        # Ubuntu

# Install Python & Git
sudo yum install python3 python3-pip git -y
# OR
sudo apt install python3 python3-pip git -y

# Install MySQL client (for testing connection)
sudo yum install mysql -y
# OR
sudo apt install mysql-client -y
```

---

## STEP 5 — Clone & Configure the App on EC2

```bash
# Clone your GitHub repo
git clone https://github.com/YOUR_USERNAME/clientvault.git

# Enter the folder
cd clientvault

# Install Python packages
pip3 install -r requirements.txt

# Create your .env file from the template
cp .env.example .env

# Edit .env with your real values
nano .env
```

### Fill in your .env:
```
FLASK_DEBUG=false
SECRET_KEY=make-this-a-long-random-string

DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=3306
DB_NAME=clientvault
DB_USER=admin
DB_PASSWORD=your-rds-password

AWS_ACCESS_KEY_ID=your-iam-access-key
AWS_SECRET_ACCESS_KEY=your-iam-secret-key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-s3-bucket-name
```
Save with Ctrl+O, exit with Ctrl+X.

---

## STEP 6 — Start the App

### Quick test (development):
```bash
python3 app.py
```
Visit: `http://YOUR-EC2-IP:5000`

If you see the ClientVault page — everything works! ✅

### Production (with Gunicorn — keeps app running):
```bash
gunicorn -c gunicorn.conf.py app:app
```

### Run in background (keeps running after you close SSH):
```bash
nohup gunicorn -c gunicorn.conf.py app:app > app.log 2>&1 &

# Check it's running:
ps aux | grep gunicorn

# View logs:
tail -f app.log
```

---

## STEP 7 — Open Port 5000 on EC2

1. AWS Console → EC2 → Security Groups
2. Find your EC2's security group → Edit Inbound Rules
3. Add rule:
   - Type: Custom TCP
   - Port: 5000
   - Source: 0.0.0.0/0

Now your app is live at: **http://YOUR-EC2-PUBLIC-IP:5000**

---

## How the 3 Tiers Work

```
TIER 1 — Presentation (Frontend)
   Browser → templates/index.html
   User fills form, drags photos

TIER 2 — Logic (Backend)
   Flask app running on EC2
   Routes: /api/clients, /api/get-upload-url
   Handles validation, S3 presigned URLs, DB writes

TIER 3 — Data
   MySQL RDS → stores client records (name, ID, address, S3 keys)
   AWS S3   → stores actual photo/document files
```

---

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Serves the frontend |
| GET | `/health` | Health check |
| POST | `/api/get-upload-url` | Get S3 presigned upload URL |
| POST | `/api/clients` | Create new client (saves to MySQL) |
| GET | `/api/clients` | List all clients |
| GET | `/api/clients/<id>` | Get one client |
| DELETE | `/api/clients/<id>` | Delete client + S3 files |

---

## Updating the App (after GitHub changes)

```bash
cd clientvault
git pull origin main
pip3 install -r requirements.txt
pkill gunicorn
nohup gunicorn -c gunicorn.conf.py app:app > app.log 2>&1 &
```

---

## Troubleshooting

**Can't connect to RDS?**
- Check your RDS security group allows port 3306 from your EC2's IP
- Double-check DB_HOST in .env (no trailing slashes)

**S3 upload fails?**
- Check your IAM user has S3FullAccess
- Check your bucket CORS policy is saved correctly
- Make sure AWS_REGION matches your bucket's region

**App won't start?**
```bash
python3 app.py   # run directly to see full error message
```
