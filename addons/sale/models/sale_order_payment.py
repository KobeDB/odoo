from .constants import SaleOrderState
from odoo.addons.payment import utils as payment_utils

from .constants import PaymentTransactionState

class SaleOrderPayment:
    def __init__(self, order):
        self.order = order
        self.env = order.env

    def _force_lines_to_invoice_policy_order(self):
        for line in self.order.order_line:
            if line.state == SaleOrderState.SALE:
                # No need to set 0 as it is already the standard logic in the compute method.
                line.qty_to_invoice = line.product_uom_qty - line.qty_invoiced
    
    def payment_action_capture(self):
        """ Capture all transactions linked to this sale order. """
        self.order.ensure_one()
        payment_utils.check_rights_on_recordset(self.order)

        # In sudo mode to bypass the checks on the rights on the transactions.
        return self.order.transaction_ids.sudo().action_capture()

    def payment_action_void(self):
        """ Void all transactions linked to this sale order. """
        payment_utils.check_rights_on_recordset(self.order)

        # In sudo mode to bypass the checks on the rights on the transactions.
        self.order.authorized_transaction_ids.sudo().action_void()
    
    def get_portal_last_transaction(self):
        self.order.ensure_one()
        return self.order.transaction_ids.sudo()._get_last()
    
    def _get_order_lines_to_report(self):
        down_payment_lines = self.order.order_line.filtered(lambda line:
            line.is_downpayment
            and not line.display_type
            and not line._get_downpayment_state()
        )

        def show_line(line):
            if not line.is_downpayment:
                return True
            elif line.display_type and down_payment_lines:
                return True  # Only show the down payment section if down payments were posted
            elif line in down_payment_lines:
                return True  # Only show posted down payments
            else:
                return False

        return self.order.order_line.filtered(show_line)

    def _get_default_payment_link_values(self):
        self.order.ensure_one()
        amount_max = self.order.amount_total - self.order.amount_paid

        # Always default to the minimum value needed to confirm the order:
        # - order is not confirmed yet
        # - can be confirmed online
        # - we have still not paid enough for confirmation.
        prepayment_amount = self.order._get_prepayment_required_amount()
        if (
            self.order.state in (str(SaleOrderState.DRAFT), str(SaleOrderState.SENT))
            and self.order.require_payment
            and self.order.currency_id.compare_amounts(prepayment_amount, self.order.amount_paid) > 0
        ):
            amount = prepayment_amount - self.order.amount_paid
        else:
            amount = amount_max

        return {
            'currency_id': self.order.currency_id.id,
            'partner_id': self.order.partner_invoice_id.id,
            'amount': amount,
            'amount_max': amount_max,
            'amount_paid': self.order.amount_paid,
        }
    
    def _compute_amount_paid(self):
        """ Sum of the amount paid through all transactions for this SO. """
        for order in self.order:
            order.amount_paid = sum(
                tx.amount for tx in order.transaction_ids if tx.state in (str(PaymentTransactionState.AUTHORIZED), str(PaymentTransactionState.DONE))
            )
