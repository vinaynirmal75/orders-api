
class OrderAPIError(Exception):
    """Base class for expected application errors."""


class CustomerNotFoundError(OrderAPIError):
    pass


class ProductNotFoundError(OrderAPIError):
    pass


class OrderNotFoundError(OrderAPIError):
    pass


class InsufficientStockError(OrderAPIError):
    pass


class DuplicateCustomerEmailError(OrderAPIError):
    pass


class OrderAlreadyCancelledError(OrderAPIError):
    pass


class InvalidOrderStateError(OrderAPIError):
    pass
