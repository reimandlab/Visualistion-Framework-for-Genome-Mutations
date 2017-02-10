from sqlalchemy.ext.associationproxy import association_proxy
from werkzeug.utils import cached_property
from database import db
from models import Model
import security
import uuid
from datetime import datetime
from datetime import timedelta
from exceptions import ValidationError


class CMSModel(Model):
    """Models descending from Model are supposed to hold settings and other data

    to handled by 'Content Managment System', including Users and Page models.
    """
    __abstract__ = True
    __bind_key__ = 'cms'


class BadWord(CMSModel):
    """Model for words which should be filtered out"""

    word = db.Column(db.Text())


class ShortURL(CMSModel):
    """Model for URL shortening entries"""

    address = db.Column(db.Text())

    alphabet = (
        'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    )

    base = len(alphabet)

    @property
    def shorthand(self):
        if self.id <= 0:
            raise ValueError('ShortURL id has to be greater than 0')

        shorthand = ''
        id_number = self.id - 1

        remainder = id_number % self.base
        id_number //= self.base
        shorthand += self.alphabet[remainder]

        while id_number:
            remainder = id_number % self.base
            id_number //= self.base
            shorthand += self.alphabet[remainder]

        return shorthand

    @staticmethod
    def shorthand_to_id(shorthand):
        id_number = 0
        for pos, letter in enumerate(shorthand):
            weight = pow(ShortURL.base, pos)
            id_number += weight * ShortURL.alphabet.index(letter)
        return id_number + 1


class User(CMSModel):
    """Model for use with Flask-Login"""

    # http://www.rfc-editor.org/errata_search.php?rfc=3696&eid=1690
    email = db.Column(db.String(254), unique=True)
    access_level = db.Column(db.Integer, default=0)
    pass_hash = db.Column(db.Text())
    datasets = db.relationship('UsersMutationsDataset', backref='owner')

    def __init__(self, email, password, access_level=0):

        if not self.is_mail_correct(email):
            raise ValidationError('This email address seems to be incorrect')

        if not self.is_password_strong(password):
            raise ValidationError('The password is not strong enough')

        self.email = email
        self.access_level = access_level
        self.pass_hash = security.generate_secret_hash(password)

    @staticmethod
    def is_mail_correct(email):

        if len(email) > 254:
            return False

        if '@' not in email:
            return False

        # both parts required
        try:
            local, domain = email.split('@')
        except ValueError:
            return False

        # no consecutive dots allowed in domain
        if '..' in domain:
            return False

        return True

    @staticmethod
    def is_password_strong(password):

        # count of different characters used
        if len(set(password)) <= 2:
            return False

        # overall length
        return len(password) >= 5

    @property
    def is_admin(self):
        return self.access_level == 10

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def authenticate(self, password):
        return security.verify_secret(password, str(self.pass_hash))

    @cached_property
    def username(self):
        return self.email.split('@')[0].replace('.', ' ').title()

    def __repr__(self):
        return '<User {0} with id {1}>'.format(
            self.email,
            self.id
        )

    def get_id(self):
        return self.id


class Page(CMSModel):
    """Model representing a single CMS page"""

    address = db.Column(
        db.String(256),
        unique=True,
        index=True,
        nullable=False,
        default='index'
    )
    title = db.Column(db.String(256))
    content = db.Column(db.Text())

    @property
    def url(self):
        """A URL-like identifier ready to be used in HTML <a> tag"""
        return '/' + self.address + '/'

    def __repr__(self):
        return '<Page /{0} with id {1}>'.format(
            self.address,
            self.id
        )


class MenuEntry(CMSModel):
    """Base for tables defining links in menu"""

    position = db.Column(db.Float, default=0)
    menu_id = db.Column(db.Integer, db.ForeignKey('menu.id'))
    type = db.Column(db.String(32))

    @property
    def title(self):
        """Name of the link"""
        raise NotImplementedError

    @property
    def url(self):
        """The href value of the link"""
        raise NotImplementedError

    __mapper_args__ = {
        'polymorphic_identity': 'entry',
        'polymorphic_on': type
    }


class PageMenuEntry(MenuEntry):
    id = db.Column(db.Integer, db.ForeignKey('menuentry.id'), primary_key=True)

    page_id = db.Column(db.Integer, db.ForeignKey('page.id'))
    page = db.relationship(
            'Page',
            backref=db.backref(
                'page_menu_entries',
                cascade='all, delete-orphan'
            )
    )

    title = association_proxy('page', 'title')
    url = association_proxy('page', 'url')

    __mapper_args__ = {
        'polymorphic_identity': 'page_entry',
    }


class CustomMenuEntry(MenuEntry):
    id = db.Column(db.Integer, db.ForeignKey('menuentry.id'), primary_key=True)

    title = db.Column(db.String(256))
    url = db.Column(db.String(256))

    __mapper_args__ = {
        'polymorphic_identity': 'custom_entry',
    }


class Menu(CMSModel):
    """Model for groups of links used as menu"""

    # name of the menu
    name = db.Column(db.String(256), nullable=False, unique=True, index=True)

    # list of all entries (links) in this menu
    entries = db.relationship('MenuEntry')


class Setting(CMSModel):

    name = db.Column(db.String(256), nullable=False, unique=True, index=True)
    value = db.Column(db.String(256))

    @property
    def int_value(self):
        return int(self.value)


class UsersMutationsDataset(CMSModel):

    data = db.Column(db.PickleType())
    name = db.Column(db.String(256))
    randomized_id = db.Column(db.String(256), unique=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_on = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def life_expectancy(self):
        """How many time is left for this dataset before removal."""
        return self.created_on - datetime.utcnow() + timedelta(days=7)

    @property
    def query_size(self):
        new_lines = self.data.query.count('\n')
        return new_lines + 1 if new_lines else 0

    @property
    def mutations(self):
        mutations = []
        results = self.data.results
        for result_obj in results.values():
            for result in result_obj['results']:
                db.session.add(result['mutation'])
                mutations.append(result['mutation'])
        return mutations

    def bind_to_session(self):
        results = self.data.results
        for name, result_obj in results.items():
            for result in result_obj['results']:
                db.session.add(result['protein'])
                db.session.add(result['mutation'])

    def assign_randomized_id(self):
        """Creates a unique ID with some random element.

        This method has to be called AFTER an id assigment by the database.
        Use of randomized ids prevents malicious software
        from iteration over all entries.
        """
        random_str = str(uuid.uuid4()).split('-')[0]
        self.randomized_id = '%s-%s' % (self.id, random_str)
