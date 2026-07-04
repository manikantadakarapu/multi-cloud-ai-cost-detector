from app.services.aws.exceptions import (
    AWSCredentialsError,
    AWSInvalidDateRangeError,
    AWSPermissionsError,
    AWSServiceError,
    AWSThrottlingError,
)


def test_aws_exceptions_hierarchy():
    """All AWS exceptions inherit from base AWSCostExplorerError."""
    base = AWSCredentialsError("No credentials")
    assert isinstance(base, Exception)
    assert str(base) == "No credentials"
    assert base.error_code == "AWS_CREDENTIALS_ERROR"

    throttling = AWSThrottlingError("Rate limited")
    assert throttling.error_code == "AWS_THROTTLING_ERROR"

    permissions = AWSPermissionsError("Access denied")
    assert permissions.error_code == "AWS_PERMISSIONS_ERROR"

    invalid_date = AWSInvalidDateRangeError("Invalid range")
    assert invalid_date.error_code == "AWS_INVALID_DATE_RANGE"

    service_error = AWSServiceError("Service error")
    assert service_error.error_code == "AWS_SERVICE_ERROR"
