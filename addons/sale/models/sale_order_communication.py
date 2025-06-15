from .constants import PaymentTransactionState, SaleOrderState
from odoo.exceptions import UserError
from odoo.tools import format_amount
from odoo import _, SUPERUSER_ID
from odoo.http import request

class SaleOrderCommunication:
    def __init__(self, order):
        self.order = order
        self.env = order.env
    
    def action_quotation_send(self):
        """ Opens a wizard to compose an email, with relevant mail template loaded by default """
        self.order.filtered(lambda so: so.state in ('draft', 'sent')).order_line._validate_analytic_distribution()
        lang = self.env.context.get('lang')

        ctx = {
            'default_model': 'sale.order',
            'default_res_ids': self.order.ids,
            'default_composition_mode': 'comment',
            'default_email_layout_xmlid': 'mail.mail_notification_layout_with_responsible_signature',
            'email_notification_allow_footer': True,
            'proforma': self.env.context.get('proforma', False),
        }

        if len(self.order) > 1:
            ctx['default_composition_mode'] = 'mass_mail'
        else:
            ctx.update({
                'force_email': True,
                'model_description': self.order.with_context(lang=lang).type_name,
            })
            if not self.env.context.get('hide_default_template'):
                mail_template = self._find_mail_template()
                if mail_template:
                    ctx.update({
                        'default_template_id': mail_template.id,
                        'mark_so_as_sent': True,
                    })
                if mail_template and mail_template.lang:
                    lang = mail_template._render_lang(self.order.ids)[self.order.id]
            else:
                for order in self.order:
                    order._portal_ensure_token()

        action = {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }
        if (
            self.env.context.get('check_document_layout')
            and not self.env.context.get('discard_logo_check')
            and self.env.is_admin()
            and not self.env.company.external_report_layout_id
        ):
            layout_action = self.env['ir.actions.report']._action_configure_external_report_layout(
                action,
            )
            # Need to remove this context for windows action
            action.pop('close_on_report_download', None)
            layout_action['context']['dialog_size'] = 'extra-large'
            return layout_action
        return action
    
    def _find_mail_template(self):
        """ Get the appropriate mail template for the current sales order based on its state.

        If the SO is confirmed, we return the mail template for the sale confirmation.
        Otherwise, we return the quotation email template.

        :return: The correct mail template based on the current status
        :rtype: record of `mail.template` or `None` if not found
        """
        self.order.ensure_one()
        if self.env.context.get('proforma') or self.order.state != 'sale':
            return self.env.ref('sale.email_template_edi_sale', raise_if_not_found=False)
        else:
            return self._get_confirmation_template()
    
    def _get_confirmation_template(self):
        """ Get the mail template sent on SO confirmation (or for confirmed SO's).

        :return: `mail.template` record or None if default template wasn't found
        """
        default_confirmation_template_id = self.env['ir.config_parameter'].sudo().get_param(
            'sale.default_confirmation_template'
        )
        default_confirmation_template = default_confirmation_template_id \
            and self.env['mail.template'].browse(int(default_confirmation_template_id)).exists()
        if default_confirmation_template:
            return default_confirmation_template
        else:
            return self.env.ref('sale.mail_template_sale_confirmation', raise_if_not_found=False)
    
    def _send_order_confirmation_mail(self):
        """ Send a mail to the SO customer to inform them that their order has been confirmed.

        :return: None
        """
        for order in self.order:
            mail_template = self._get_confirmation_template()
            order._send_order_notification_mail(mail_template)
    
    def action_quotation_sent(self):
        """ Mark the given draft quotation(s) as sent.

        :raise: UserError if any given SO is not in draft state.
        """
        if any(order.state != 'draft' for order in self.order):
            raise UserError(_("Only draft orders can be marked as sent directly."))

        for order in self.order:
            order.message_subscribe(partner_ids=order.partner_id.ids)

        self.order.write({'state': 'sent'})
    
    def _notify_get_recipients_groups(self, groups, msg_vals=None):
        """ Give access button to users and portal customer as portal is integrated
        in sale. Customer and portal group have probably no right to see
        the document so they don't have the access button. """
        if not self.order:
            return groups

        self.order.ensure_one()
        if self.order._context.get('proforma'):
            for group in [g for g in groups if g[0] in ('portal_customer', 'portal', 'follower', 'customer')]:
                group[2]['has_button_access'] = False
            return groups
        local_msg_vals = dict(msg_vals or {})

        # portal customers have full access (existence not granted, depending on partner_id)
        try:
            customer_portal_group = next(group for group in groups if group[0] == 'portal_customer')
        except StopIteration:
            pass
        else:
            access_opt = customer_portal_group[2].setdefault('button_access', {})
            is_tx_pending = self.order.get_portal_last_transaction().state == PaymentTransactionState.PENDING
            if self.order._has_to_be_signed():
                if self.order._has_to_be_paid():
                    access_opt['title'] = _("View Quotation") if is_tx_pending else _("Sign & Pay Quotation")
                else:
                    access_opt['title'] = _("Accept & Sign Quotation")
            elif self.order._has_to_be_paid() and not is_tx_pending:
                access_opt['title'] = _("Accept & Pay Quotation")
            elif self.order.state in ('draft', 'sent'):
                access_opt['title'] = _("View Quotation")

        # enable followers that have access through portal
        follower_group = next(group for group in groups if group[0] == 'follower')
        follower_group[2]['active'] = True
        follower_group[2]['has_button_access'] = True
        access_opt = follower_group[2].setdefault('button_access', {})
        if self.order.state in ('draft', 'sent'):
            access_opt['title'] = _("View Quotation")
        else:
            access_opt['title'] = _("View Order")
        access_opt['url'] = self.order._notify_get_action_link('view', **local_msg_vals)

        return groups
    
    def _notify_by_email_prepare_rendering_context(self, render_context):
        lang_code = render_context.get('lang')
        record = render_context['record']
        subtitles = [f"{record.name} - {record.partner_id.name}" if record.partner_id else record.name]
        if self.order.amount_total:
            # Do not show the price in subtitles if zero (e.g. e-commerce orders are created empty)
            subtitles.append(
                format_amount(self.env, self.order.amount_total, self.order.currency_id, lang_code=lang_code),
            )

        render_context['subtitles'] = subtitles
        return render_context
    
    def prepare_message_post_kwargs(self, kwargs):
        order = self.order
        if self.env.context.get('mark_so_as_sent'):
            order.filtered(lambda o: o.state == SaleOrderState.DRAFT).with_context(tracking_disable=True).write({'state': 'sent'})
        so_ctx = {'mail_post_autofollow': self.env.context.get('mail_post_autofollow', True)}
        if self.env.context.get('mark_so_as_sent') and 'mail_notify_author' not in kwargs:
            kwargs = kwargs.copy()
            kwargs['notify_author'] = self.env.user.partner_id.id in (kwargs.get('partner_ids') or [])
        return so_ctx, kwargs

    def _track_subtype(self, init_values):
        self.order.ensure_one()
        if 'state' in init_values and self.order.state == SaleOrderState.SALE:
            return self.env.ref('sale.mt_order_confirmed')
        elif 'state' in init_values and self.order.state == SaleOrderState.SENT:
            return self.env.ref('sale.mt_order_sent')
        return None
    
    def _message_get_suggested_recipients(self, recipients):
        if self.order.partner_id:
            self.order._message_add_suggested_recipient(
                recipients, partner=self.order.partner_id, reason=_("Customer")
            )
        return recipients
    
    def should_discard_tracking(self):
        return (len(self.order) == 1
            and self.env.cache.contains(self.order, self.order._fields['state']) 
            and self.order._discard_tracking())
    
    def _send_order_notification_mail(self, mail_template):
        """ Send a mail to the customer

        Note: self.ensure_one()

        :param mail.template mail_template: the template used to generate the mail
        :return: None
        """
        self.order.ensure_one()

        if not mail_template:
            return

        if self.env.su:
            # sending mail in sudo was meant for it being sent from superuser
            self.order = self.order.with_user(SUPERUSER_ID)

        self.order.with_context(force_send=True).message_post_with_source(
            mail_template,
            email_layout_xmlid='mail.mail_notification_layout_with_responsible_signature',
            subtype_xmlid='mail.mt_comment',
        )
    
    def _send_payment_succeeded_for_order_mail(self):
        """ Send a mail to the SO customer to inform them that a payment has been initiated.

        :return: None
        """
        mail_template = self.env.ref(
            'sale.mail_template_sale_payment_executed', raise_if_not_found=False
        )
        for order in self.order:
            order._send_order_notification_mail(mail_template)
    
    def _discard_tracking(self):
        self.order.ensure_one()
        return (
            self.order.state == SaleOrderState.DRAFT
            and request and request.env.context.get('catalog_skip_tracking')
        )