class SaleOrderPortal:
    def __init__(self, order):
        self.order = order
        self.env = order.env

    def _has_to_be_signed(self):
        """A sale order has to be signed when:
        - its state is 'draft' or `sent`
        - it's not expired;
        - it requires a signature;
        - it's not already signed.

        Note: self.ensure_one()

        :return: Whether the sale order has to be signed.
        :rtype: bool
        """
        self.order.ensure_one()
        return (
            self.order.state in ['draft', 'sent']
            and not self.order.is_expired
            and self.order.require_signature
            and not self.order.signature
        )

    def _has_to_be_paid(self):
        """A sale order has to be paid when:
        - its state is 'draft' or `sent`;
        - it's not expired;
        - it requires a payment;
        - the last transaction's state isn't `done`;
        - the total amount is strictly positive.
        - confirmation amount is not reached

        Note: self.ensure_one()

        :return: Whether the sale order has to be paid.
        :rtype: bool
        """
        self.order.ensure_one()
        return (
            self.order.state in ['draft', 'sent']
            and not self.order.is_expired
            and self.order.require_payment
            and self.order.amount_total > 0
            and not self.order._is_confirmation_amount_reached()
        )

    def _get_portal_return_action(self):
        """ Return the action used to display orders when returning from customer portal. """
        self.order.ensure_one()
        return self.env.ref('sale.action_quotations_with_onboarding')
    
    def _get_name_portal_content_view(self):
        """ This method can be inherited by localizations who want to localize the online quotation view. """
        self.order.ensure_one()
        return 'sale.sale_order_portal_content'
    
    def _get_name_tax_totals_view(self):
        """ This method can be inherited by localizations who want to localize the taxes displayed on the portal and sale order report. """
        return 'sale.document_tax_totals'
    
    def _get_report_base_filename(self):
        self.order.ensure_one()
        return f'{self.order.type_name} {self.order.name}'

