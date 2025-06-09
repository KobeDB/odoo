from enum import Enum

# My own StrEnum implementation ( to keep compatibility with python versions < 3.11)
class StrEnum(str, Enum):
    def __str__(self):
        return str(self.value)

""" terms_type in sale/sale_order.py """
class TermsType(StrEnum):
    PLAIN = 'plain'
    HTML  = 'html'

""" early_pay_discount_computation in account/account_payment_term.py """
class EarlyPayDiscountComputation(StrEnum):
    INCLUDED = 'included'
    EXCLUDED = 'excluded'
    MIXED    = 'mixed'

""" invoice_status in sale/sale_order.py """
class InvoiceStatus(StrEnum):
    UPSELLING  = 'upselling'
    INVOICED   = 'invoiced'
    TO_INVOICE = 'to invoice'
    NO         = 'no'

""" state in sale/sale_order.py """
class SaleOrderState(StrEnum):
    DRAFT  = 'draft'
    SENT   = 'sent'
    SALE   = 'sale'
    CANCEL = 'cancel'

""" state in payment/payment_transaction.py """
class PaymentTransactionState(StrEnum):
    DRAFT      = 'draft'
    PENDING    = 'pending'
    AUTHORIZED = 'authorized'
    DONE       = 'done'
    CANCEL     = 'cancel'
    ERROR      = 'error'

""" WARNING_MESSAGE in base/res_partner.py """
class WarningMessage(StrEnum):
    NO_MESSAGE = 'no-message'
    WARNING    = 'warning'
    BLOCK      = 'block'

""" product_type in sale/sale_order_line.py"""
class ProductType(StrEnum):
    CONSU   = 'consu'
    SERVICE = 'service'
    COMBO   = 'combo'

""" state in account/account_move.py """
class AccountMoveState(StrEnum):
    DRAFT  = 'draft'
    POSTED = 'posted'
    CANCEL = 'cancel'

""" type in sale/sale_order_line.py """
class OrderLineDisplayType(StrEnum):
    LINE_SECTION = 'line_section'
    LINE_NOTE    = 'line_note'

""" account_type in account/account_account.py """
class AccountType(StrEnum):
    ASSET_RECEIVABLE = 'asset_receivable'

""" display_type in account/account_move_line.py """
class AccountMoveLineDisplayType(StrEnum):
    PRODUCT      = 'product'
    COGS         = 'cogs'
    TAX          = 'tax'
    DISCOUNT     = 'discount'
    ROUNDING     = 'rounding'
    PAYMENT_TERM = 'payment_term'
    LINE_SECTION = 'line_section'
    LINE_NOTE    = 'line_note'
    EPD          = 'epd'

""" attached_on_sale in sale/product_document.py """
class AttachedOnSale(StrEnum):
    HIDDEN     = 'hidden'
    QUOTATION  = 'quotation'
    SALE_ORDER = 'sale_order'
