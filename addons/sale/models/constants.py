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

""" operation in sale/payment_transaction.py """
class PaymentTransactionOperation(StrEnum):
    ONLINE_REDIRECT = 'online_redirect'
    ONLINE_DIRECT   = 'online_direct'
    ONLINE_TOKEN    = 'online_token'
    VALIDATION      = 'validation'
    OFFLINE         = 'offline'
    REFUND          = 'refund'

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

""" state in account/account_payment.py """
class AccountPaymentState(StrEnum):
    DRAFT       = 'draft'
    IN_PROCESS  = 'in_process'
    PAID        = 'paid'
    CANCELED    = 'canceled'
    REJECTED    = 'rejected'

""" account_type in account/account """
class AccountAccountType(StrEnum):
    ASSET_RECEIVABLE    = 'asset_receivable'
    ASSET_CASH          = 'asset_cash'
    ASSET_CURRENT       = 'asset_current'
    ASSET_NON_CURRENT   = 'asset_non_current'
    ASSET_PREPAYMENTS   = 'asset_prepayments'
    ASSET_FIXED         = 'asset_fixed'

    LIABILITY_PAYABLE     = 'liability_payable'
    LIABILITY_CREDIT_CARD = 'liability_credit_card'
    LIABILITY_CURRENT     = 'liability_current'
    LIABILITY_NON_CURRENT = 'liability_non_current'

    EQUITY              = 'equity'
    EQUITY_UNAFFECTED   = 'equity_unaffected'

    INCOME          = 'income'
    INCOME_OTHER    = 'income_other'

    EXPENSE                 = 'expense'
    EXPENSE_DEPRECIATION    = 'expense_depreciation'
    EXPENSE_DIRECT_COST     = 'expense_direct_cost'

    OFF_BALANCE = 'off_balance'

""" payment_state in account/account_move.py """
class AccountMovePaymentState(StrEnum):
    NOT_PAID            = 'not_paid'
    IN_PAYMENT          = 'in_payment'
    PAID                = 'paid'
    PARTIAL             = 'partial'
    REVERSED            = 'reversed'
    BLOCKED             = 'blocked'
    INVOICING_LEGACY    = 'invoicing_legacy'

""" move_type in account/account_move.py """
class AccountMoveType(StrEnum):
    ENTRY       = 'entry'
    OUT_INVOICE = 'out_invoice'
    OUT_REFUND  = 'out_refund'
    IN_INVOICE  = 'in_invoice'
    IN_REFUND   = 'in_refund'
    OUT_RECEIPT = 'out_receipt'
    IN_RECEIPT  = 'in_receipt'

""" expense_policy in sale/product_template.py """
class ProductTemplateExpensePolicy(StrEnum):
    NO          = 'no'
    COST        = 'cost'
    SALES_PRICE = 'sales_price'

""" invoice_policy in sale/product_template.py """
class ProductTemplateInvoicePolicy(StrEnum):
    ORDER       = 'order'
    DELIVERY    = 'delivery'

""" service_type in sale/product_template.py """
class ProductTemplateServiceType(StrEnum):
    MANUAL = 'manual'

"""  """
class SaleOrderLineQtyDeliveredMethod(StrEnum):
    MANUAL      = 'manual'
    ANALYTIC    = 'analytic'

""" so_reference_type in sale/payment_provider.py """
class PaymentProviderSoReferenceType(StrEnum):
    SO_NAME = 'so_name'
    PARTNER = 'partner'

""" type in account/account_journal.py """
class AccountJournalType(StrEnum):
    SALE        = 'sale'
    PURCHASE    = 'purchase'
    CASH        = 'cash'
    BANK        = 'bank'
    CREDIT      = 'credit'
    GENERAL     = 'general'

""" sale_onboarding_payment_method in sale/res_company.py """
class SaleOnboardingPaymentMethod(StrEnum):
    DIGITAL_SIGNATURE   = 'digital_signature'
    PAYPAL              = 'paypal'
    STRIPE              = 'stripe'
    OTHER               = 'other'
    MANUAL              = 'manual'

""" composition_mode in mail/wizard/mail_compose_message.py """
class MailCompositionMode(StrEnum):
    COMMENT = 'comment'
    MASS_MAIL = 'mass_mail'

""" advance_payment_method in sale/wizard/sale_make_invoice_advance.py """
class SaleAdvancePaymentMethod(StrEnum):
    DELIVERED = 'delivered'
    PERCENTAGE = 'percentage'
    FIXED = 'fixed'

""" display_type in product/product_attribute.py """
class ProductAttributeDisplayType(StrEnum):
    RADIO  = 'radio'
    PILLS  = 'pills'
    SELECT = 'select'
    COLOR  = 'color'
    MULTI  = 'multi'
