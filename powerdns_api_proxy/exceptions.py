from fastapi import HTTPException


class ZoneNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Zone not allowed"


class ZoneAdminNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Not Zone admin"


class RecordNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Record not allowed"


class RessourceNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Ressource not allowed"


class NotAuthorizedException(HTTPException):
    def __init__(self):
        self.status_code = 401
        self.detail = "Unauthorized"


class SearchNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Search not allowed"


class MetricsNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Metrics not allowed"


class UpstreamException(HTTPException):
    def __init__(self, message: str | None = None):
        self.status_code = 500
        self.detail = message or "Error while connecting to PowerDNS backend"


class UnhandledException(HTTPException):
    def __init__(self, message: str | None = None):
        self.status_code = 500
        self.detail = message or "Unhandled error"
