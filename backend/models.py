from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc)

class Batch(db.Model):
    """Batches model for grouping recording uploads."""
    __tablename__ = 'batches'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_name = db.Column(db.String(255), nullable=False)
    keywords = db.Column(db.String(500), nullable=True)
    destination_folder = db.Column(db.String(500), nullable=True)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    total_files = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(50), default='active', nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    uploads = db.relationship('Upload', backref='batch', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'batch_name': self.batch_name,
            'keywords': self.keywords,
            'destination_folder': self.destination_folder,
            'is_enabled': self.is_enabled,
            'total_files': self.total_files,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Batch id={self.id} name='{self.batch_name}' enabled={self.is_enabled}>"


class Upload(db.Model):
    """Uploads model representing recording files."""
    __tablename__ = 'uploads'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id', ondelete='SET NULL'), nullable=True)
    batch_name = db.Column(db.String(100), nullable=True)
    original_file_name = db.Column(db.String(255), nullable=True)
    original_file_path = db.Column(db.String(500), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger, default=0, nullable=False)
    file_extension = db.Column(db.String(20), nullable=True)
    upload_date = db.Column(db.Date, nullable=True)
    upload_time = db.Column(db.String(20), nullable=True)
    checksum = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(50), default='pending', nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    queue_items = db.relationship('ProcessingQueue', backref='upload', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'batch_name': self.batch_name,
            'original_file_name': self.original_file_name,
            'original_file_path': self.original_file_path,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'file_extension': self.file_extension,
            'upload_date': self.upload_date.isoformat() if self.upload_date else (self.uploaded_at.strftime('%Y-%m-%d') if self.uploaded_at else None),
            'upload_time': self.upload_time or (self.uploaded_at.strftime('%H:%M:%S') if self.uploaded_at else None),
            'checksum': self.checksum,
            'status': self.status,
            'error_message': self.error_message,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Upload id={self.id} file='{self.file_name}' status='{self.status}'>"


class Setting(db.Model):
    """System configuration settings stored in database."""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(255), nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Setting key='{self.key}' value='{self.value}'>"


class ProcessingQueue(db.Model):
    """Queue items for asynchronous upload processing tasks."""
    __tablename__ = 'processing_queue'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    upload_id = db.Column(db.Integer, db.ForeignKey('uploads.id', ondelete='CASCADE'), nullable=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id', ondelete='SET NULL'), nullable=True)
    file_name = db.Column(db.String(255), nullable=True)
    file_path = db.Column(db.String(500), nullable=True, unique=True, index=True)
    detected_batch = db.Column(db.String(255), nullable=True)
    standardized_name = db.Column(db.String(255), nullable=True)
    validation_status = db.Column(db.String(50), default='Pending', nullable=False)
    task_type = db.Column(db.String(100), default='file_detection', nullable=False)
    payload = db.Column(db.Text, nullable=True)
    priority = db.Column(db.Integer, default=0, nullable=False)
    status = db.Column(db.String(50), default='Pending', nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    file_size = db.Column(db.BigInteger, default=0, nullable=False)
    detected_time = db.Column(db.DateTime, default=utcnow, nullable=False)
    completed_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    batch = db.relationship('Batch', backref='queued_items', foreign_keys=[batch_id])

    def to_dict(self):
        return {
            'id': self.id,
            'upload_id': self.upload_id,
            'batch_id': self.batch_id,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'detected_batch': self.detected_batch,
            'standardized_name': self.standardized_name,
            'validation_status': self.validation_status,
            'task_type': self.task_type,
            'payload': self.payload,
            'priority': self.priority,
            'status': self.status,
            'attempts': self.attempts,
            'error_message': self.error_message,
            'file_size': self.file_size,
            'detected_time': self.detected_time.isoformat() if self.detected_time else None,
            'completed_time': self.completed_time.isoformat() if self.completed_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<ProcessingQueue id={self.id} file='{self.file_name}' std='{self.standardized_name}' status='{self.status}'>"
