# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import boto3
import logging
from botocore.client import Config

logger = logging.getLogger(__name__)

class StorageService(object):

    def __init__(self):
        self.access_key_id = os.getenv('BUCKET_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('BUCKET_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('BUCKET_NAME')
        self.region_name = os.getenv('BUCKET_DEFAULT_REGION') or 'us-east-1'
        self.storage_type = os.getenv('CALLREC_DEVICE')
        
        # 1. Definición de Endpoints
        # Endpoint Público (Para el navegador JS) -> https://localhost/minio
        self.public_endpoint = os.getenv('BUCKET_ENDPOINT')
        
        # Endpoint Interno (Para Django) -> http://minio:9000
        # Si no está definida la interna, usamos la pública como fallback
        self.internal_endpoint = os.getenv('BUCKET_ENDPOINT_INTERNAL') or self.public_endpoint

        # Configuración de SSL (según tu lógica original)
        verify_ssl = True
        if self.storage_type == 's3-no-check-cert':
            verify_ssl = False

        # Configuración Boto3 (Signature V4 es estándar para MinIO/S3)
        boto_config = Config(signature_version='s3v4')

        # ---------------------------------------------------------
        # CLIENTE 1: OPERATIVO (Backend -> S3)
        # ---------------------------------------------------------
        # Este cliente se usa para upload_file, download_file, delete_object
        self.op_client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=boto_config,
            endpoint_url=self.internal_endpoint,
            region_name=self.region_name,
            verify=verify_ssl
        )

        # ---------------------------------------------------------
        # CLIENTE 2: FIRMANTE (Browser -> Nginx -> S3)
        # ---------------------------------------------------------
        # Este cliente SOLO se usa para generate_presigned_url
        self.signer_client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=boto_config,
            endpoint_url=self.public_endpoint,
            region_name=self.region_name,
            verify=verify_ssl
        )

    def get_file_url(self, filename):
        """
        Genera la URL firmada usando el cliente INTERNO y reemplaza el dominio.
        """
        try:
            # Validación de seguridad
            if not filename:
                return None

            # Key: Aseguramos que no tenga slash inicial
            key = filename[1:] if filename.startswith('/') else filename
            
            # 1. FIRMAMOS usando el cliente INTERNO (op_client)
            # Esto usa la configuración de self.internal_endpoint definida en __init__
            url = self.op_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=3600
            )

            # 2. REEMPLAZAMOS el dominio interno por el público
            # CORRECCIÓN AQUÍ: Usamos self.internal_endpoint en lugar de self.internal_url
            if self.internal_endpoint and self.public_endpoint:
                internal_base = self.internal_endpoint.rstrip('/')
                public_base = self.public_endpoint.rstrip('/')
                
                # Reemplazo seguro
                url = url.replace(internal_base, public_base)

            return url
            
        except Exception as e:
            logger.error(f'Error generando URL firmada: {e}')
            return None

    def download_file(self, file_name, local_destination, root_s3_folder=None):
        """
        Descarga archivo desde S3 al sistema de archivos LOCAL de Django.
        Usa el 'op_client' (Endpoint Interno).
        """
        file_dest = os.path.join(local_destination, file_name)
        full_local_path = os.path.dirname(file_dest)
        
        if not os.path.exists(full_local_path):
            try:
                os.makedirs(full_local_path, mode=0o755)
            except Exception:
                pass
        
        try:
            s3_file_path = file_name
            if root_s3_folder is not None:
                s3_file_path = f'{root_s3_folder}/{s3_file_path}'
            
            # Usamos el cliente operativo (interno)
            self.op_client.download_file(self.bucket_name, s3_file_path, file_dest)
            
        except Exception as e:
            logger.error(f'Error descargando archivo {s3_file_path} desde S3 {e.__str__()}')
            return False
        return True

    def upload_file(self, filename, local_path, remote_destination):
        """
        Sube archivo desde Django hacia S3.
        Usa el 'op_client' (Endpoint Interno).
        """
        file_dest = os.path.join(remote_destination, filename)
        try:
            # Usamos el cliente operativo (interno)
            self.op_client.upload_file(local_path, self.bucket_name, file_dest)
        except Exception as e:
            logger.error(f'Error subiendo archivo desde S3 {e.__str__()}')
            return False
        return True

    def delete_file(self, filename, remote_destination):
        """
        Borra archivo en S3.
        Usa el 'op_client' (Endpoint Interno).
        """
        file_dest = os.path.join(remote_destination, filename)
        try:
            # Usamos el cliente operativo (interno)
            self.op_client.delete_object(Bucket=self.bucket_name, Key=file_dest)
        except Exception as e:
            logger.error(f'Error borrando archivo desde S3 {e.__str__()}')
            return False
        return True