from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import boto3
from botocore.exceptions import ClientError
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ─── Database Config ───────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─── S3 Config ─────────────────────────────────────────────────
# No keys needed here — boto3 automatically uses the EC2 IAM Role
s3_client = boto3.client(
    's3',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
)
S3_BUCKET = os.getenv('S3_BUCKET_NAME')


# ─── Database Models ────────────────────────────────────────────
class Client(db.Model):
    __tablename__ = 'clients'

    id           = db.Column(db.Integer, primary_key=True)
    client_id    = db.Column(db.String(50), unique=True, nullable=False)
    first_name   = db.Column(db.String(100), nullable=False)
    last_name    = db.Column(db.String(100), nullable=False)
    email        = db.Column(db.String(150), nullable=False)
    phone        = db.Column(db.String(30))
    dob          = db.Column(db.String(20))
    street       = db.Column(db.String(255))
    city         = db.Column(db.String(100))
    state        = db.Column(db.String(100))
    zip_code     = db.Column(db.String(20))
    country      = db.Column(db.String(100))
    notes        = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    pictures     = db.relationship('ClientPicture', backref='client', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':         self.id,
            'client_id':  self.client_id,
            'first_name': self.first_name,
            'last_name':  self.last_name,
            'email':      self.email,
            'phone':      self.phone,
            'dob':        self.dob,
            'address': {
                'street':  self.street,
                'city':    self.city,
                'state':   self.state,
                'zip':     self.zip_code,
                'country': self.country,
            },
            'notes':      self.notes,
            'pictures':   [p.to_dict() for p in self.pictures],
            'created_at': self.created_at.isoformat(),
        }


class ClientPicture(db.Model):
    __tablename__ = 'client_pictures'

    id         = db.Column(db.Integer, primary_key=True)
    client_id  = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    s3_key     = db.Column(db.String(500), nullable=False)
    file_name  = db.Column(db.String(255))
    file_type  = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        url = f"https://{S3_BUCKET}.s3.amazonaws.com/{self.s3_key}"
        return {
            'id':        self.id,
            's3_key':    self.s3_key,
            'file_name': self.file_name,
            'file_type': self.file_type,
            'url':       url,
        }


# ─── Routes ────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': datetime.utcnow().isoformat()})


# Generate presigned S3 URL so browser uploads directly to S3
@app.route('/api/get-upload-url', methods=['POST'])
def get_upload_url():
    data      = request.get_json()
    file_name = data.get('fileName', 'file')
    file_type = data.get('fileType', 'application/octet-stream')
    client_id = data.get('clientId', 'unknown')

    s3_key = f"clients/{client_id}/{uuid.uuid4()}_{file_name}"

    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket':      S3_BUCKET,
                'Key':         s3_key,
                'ContentType': file_type,
            },
            ExpiresIn=300  # 5 minutes
        )
        return jsonify({'uploadUrl': presigned_url, 'key': s3_key})
    except ClientError as e:
        return jsonify({'error': str(e)}), 500


# Save client record + S3 keys to MySQL
@app.route('/api/clients', methods=['POST'])
def create_client():
    data = request.get_json()

    # Check for duplicate client ID
    if Client.query.filter_by(client_id=data.get('clientId')).first():
        return jsonify({'error': 'Client ID already exists'}), 409

    address = data.get('address', {})

    client = Client(
        client_id  = data.get('clientId'),
        first_name = data.get('firstName'),
        last_name  = data.get('lastName'),
        email      = data.get('email'),
        phone      = data.get('phone'),
        dob        = data.get('dob'),
        street     = address.get('street'),
        city       = address.get('city'),
        state      = address.get('state'),
        zip_code   = address.get('zip'),
        country    = address.get('country'),
        notes      = data.get('notes'),
    )
    db.session.add(client)
    db.session.flush()  # get client.id before commit

    # Save S3 keys for each uploaded picture
    for pic in data.get('pictures', []):
        picture = ClientPicture(
            client_id = client.id,
            s3_key    = pic.get('key'),
            file_name = pic.get('fileName'),
            file_type = pic.get('fileType'),
        )
        db.session.add(picture)

    db.session.commit()
    return jsonify({'message': 'Client registered', 'clientId': client.client_id, 'id': client.id}), 201


# Get all clients
@app.route('/api/clients', methods=['GET'])
def get_clients():
    clients = Client.query.order_by(Client.created_at.desc()).all()
    return jsonify([c.to_dict() for c in clients])


# Get single client
@app.route('/api/clients/<client_id>', methods=['GET'])
def get_client(client_id):
    client = Client.query.filter_by(client_id=client_id).first_or_404()
    return jsonify(client.to_dict())


# Delete client + their S3 files
@app.route('/api/clients/<client_id>', methods=['DELETE'])
def delete_client(client_id):
    client = Client.query.filter_by(client_id=client_id).first_or_404()

    # Delete files from S3
    for pic in client.pictures:
        try:
            s3_client.delete_object(Bucket=S3_BUCKET, Key=pic.s3_key)
        except ClientError:
            pass  # continue even if S3 delete fails

    db.session.delete(client)
    db.session.commit()
    return jsonify({'message': f'Client {client_id} deleted'})


# ─── Init DB ────────────────────────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database tables created")
    app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true')
