from odoo.exceptions import UserError, RedirectWarning
import logging
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)

class SaleOrderEDI:
    def __init__(self, order):
        self.order = order
        self.env = order.env

    def create_document_from_attachment(self, attachment_ids):
        """ Create the sale orders from given attachment_ids and redirect newly create order view.

        :param list attachment_ids: List of attachments process.
        :return: An action redirecting to related sale order view.
        :rtype: dict
        """
        orders = self.order._create_order_from_attachment(attachment_ids)
        return orders._get_records_action(name=_("Generated Orders"))

    def _create_order_from_attachment(self, attachment_ids):
        """ Create the sale orders from given attachment_ids and fill data by extracting detail
        from attachments and return generated orders.

        :param list attachment_ids: List of attachments process.
        :return: Recordset of order.
        """
        attachments = self.env['ir.attachment'].browse(attachment_ids)
        if not attachments:
            raise UserError(_("No attachment was provided"))

        orders = self.order.browse()
        for attachment in attachments:
            order = self.order.create({
                'partner_id': self.env.user.partner_id.id,
            })
            order._extend_with_attachments(attachment)
            orders |= order
            order.message_post(attachment_ids=attachment.ids)
            attachment.write({'res_model': self.order._name, 'res_id': order.id})

        return orders
    
    def _extend_with_attachments(self, attachment):
        """ Main entry point to extend/enhance order with attachment.

        :param attachment: A recordset of ir.attachment.
        :returns: None
        """
        self.order.ensure_one()

        file_data = attachment._unwrap_edi_attachments()[0]
        decoder = self.order._get_order_edi_decoder(file_data)
        if decoder:
            try:
                with self.env.cr.savepoint():
                    decoder(self, file_data)
            except RedirectWarning:
                raise
            except Exception:
                message = _(
                    "Error importing attachment '%(file_name)s' as order (decoder=%(decoder)s)",
                    file_name=file_data['filename'],
                    decoder=decoder.__name__,
                )
                self.order.with_user(SUPERUSER_ID).message_post(body=message)
                _logger.exception(message)

        if file_data.get('on_close'):
            file_data['on_close']()
        return True

    def _get_order_edi_decoder(self, file_data):
        """ To be extended with decoding capabilities of order data from file data.

        :returns:  Function to be later used to import the file.
                   Function' args:
                   - order: sale.order
                   - file_data: attachemnt information / value
                   returns True if was able to process the order
        """
        if file_data['type'] in ('pdf', 'binary'):
            return lambda *args: False
        return