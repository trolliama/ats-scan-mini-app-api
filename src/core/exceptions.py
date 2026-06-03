class DuplicateScanError(Exception):
    pass


class ScanNotFound(Exception):
    pass


class S3ObjectNotFoundError(Exception):
    # Deferred: raised by infra/storage/s3.py
    pass
