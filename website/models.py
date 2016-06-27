from database import db
from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy.sql import exists, select
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy.ext.hybrid import hybrid_property
from werkzeug.utils import cached_property


def make_association_table(fk1, fk2):
    """Create an association table basing on names of two given foreign keys.

    From keys: `site.id` and `kinase.id` a table named: site_kinase_association
    will be created and it will contain two columns: `site_id` and `kinase_id`.
    """
    table_name = '%s_%s_association' % (fk1.split('.')[0], fk2.split('.')[0])
    return db.Table(
        table_name, db.metadata,
        db.Column(fk1.replace('.', '_'), db.Integer, db.ForeignKey(fk1)),
        db.Column(fk2.replace('.', '_'), db.Integer, db.ForeignKey(fk2)),
    )


class Kinase(db.Model):
    __tablename__ = 'kinase'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, index=True)
    protein_id = db.Column(db.Integer, db.ForeignKey('protein.id'))
    group_id = db.Column(db.Integer, db.ForeignKey('kinase_group.id'))


class KinaseGroup(db.Model):
    __tablename__ = 'kinase_group'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, index=True)
    kinases = db.relationship(
        'Kinase',
        order_by='Kinase.name',
        backref='group'
    )


class Protein(db.Model):
    __tablename__ = 'protein'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, index=True)
    refseq = db.Column(db.String(32), unique=True)
    sequence = db.Column(db.Text)
    disorder_map = db.Column(db.Text)
    sites = db.relationship(
        'Site',
        order_by='Site.position',
        backref='protein'
    )
    mutations = db.relationship(
        'Mutation',
        order_by='Mutation.position',
        lazy='dynamic',
        backref='protein'
    )
    kinase = db.relationship(
        'Kinase',
        backref='protein'
    )

    def __init__(self, name):
        self.name = name
        self.sequence = ''
        self.disorder_map = ''

    def __repr__(self):
        return '<Protein %r>' % self.name

    @cached_property
    def length(self):
        """Length of protein's sequence"""
        return len(self.sequence)

    @cached_property
    def mutations_grouped(self):
        """Mutations grouped by cancer type and position in the sequence"""
        mutations_grouped = {}
        for mutation in self.mutations:
            # for now, I am grouping just by position and cancer

            key = (mutation.position,
                   mutation.mut_residue,
                   mutation.cancer.name)
            try:
                mutations_grouped[key] += [mutation]
            except KeyError:
                mutations_grouped[key] = [mutation]
        return mutations_grouped

    @cached_property
    def disorder_regions(self):
        """Transform binary disorder data into list of spans.

        Each span is represented by a tuple: (start, length).
        The coordinates are 1-based.
        """

        disorder_regions = []
        inside_region = False

        for i in range(len(self.disorder_map)):
            residue = int(self.disorder_map[i])
            if inside_region:
                if not residue:
                    inside_region = False
                    disorder_regions[-1][1] = i - disorder_regions[-1][0]
            else:
                if residue:
                    disorder_regions += [[i + 1, 1]]
                    inside_region = True

        return disorder_regions

    @hybrid_property
    def kinases(self):
        """Get all kinases associated with this protein"""
        kinases = set()
        # first of all we need kinases to be a foreign key to proteins
        for site in self.sites:
            kinases.update((site.kinases))
        return kinases

    @kinases.expression
    def kinases(self):
        """SQL expression for kinases"""
        q = select(Protein.sites.kinases).\
            distinct()
        return db.session.query(q)

    @hybrid_property
    def kinase_groups(self):
        """Get all kinase_groups associated with this protein"""
        kinase_groups = set()
        for site in self.sites:
            kinase_groups.update((site.kinase_groups))
        return kinase_groups


class Site(db.Model):
    __tablename__ = 'site'
    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.Integer, index=True)
    residue = db.Column(db.String(1))
    pmid = db.Column(db.Text)
    protein_id = db.Column(db.Integer, db.ForeignKey('protein.id'))
    kinases = db.relationship(
        'Kinase',
        secondary=make_association_table('site.id', 'kinase.id')
    )
    kinase_groups = db.relationship(
        'KinaseGroup',
        secondary=make_association_table('site.id', 'kinase_group.id')
    )

    def __repr__(self):
        return '<Site of protein: {0}, at pos: {1}>'.format(
            Protein.query.get(self.protein_id).name,
            self.position
        )


class Cancer(db.Model):
    __tablename__ = 'cancer'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16))
    name = db.Column(db.Text)
    mutations = db.relationship('Mutation', backref='cancer')

    def __repr__(self):
        return '<Cancer with code: {0}, named: {1}>'.format(
            self.code,
            self.name
        )


class Mutation(db.Model):
    __tablename__ = 'mutation'
    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.Integer)
    wt_residue = db.Column(db.String(1))
    mut_residue = db.Column(db.String(1))
    sample_id = db.Column(db.String(64))
    cancer_id = db.Column(db.Integer, db.ForeignKey('cancer.id'))
    protein_id = db.Column(db.Integer, db.ForeignKey('protein.id'))

    def __init__(self, cancer, sample_id,
                 position, wt_residue, mut_residue, protein):
        self.cancer = cancer
        self.sample_id = sample_id
        self.position = position
        self.wt_residue = wt_residue
        self.mut_residue = mut_residue
        self.protein = protein

    # Note: following properties could become a columns of the database tables
    # (in the future) to avoid repetitive calculation of constant variables.
    # Nonetheless making decision about each of these should take into account,
    # how often columns and other models referenced in property will be updated
    # (so we can avoid unnecessary whole database rebuilding).

    # We can also use SQL Materialized View
    # For MySQL manual implementation is needed but it is quite straightforward

    @hybrid_property
    def is_ptm(self):
        """Mutation is PTM related if it may affect PTM site.

        Mutations flanking PTM site in a distance up to 7 residues from
        a site (called here 'distal') will be included too.
        """
        return self.is_ptm_distal

    @hybrid_property
    def is_ptm_direct(self):
        """True if the mutation is on the same position as some PTM site."""
        return self.is_close_to_some_site(0, 0)

    @hybrid_property
    def is_ptm_proximal(self):
        """Check if the mutation is in close proximity of some PTM site.

        Proximity is defined here as [pos - 3, pos + 3] span,
        where pos is the position of a PTM site.
        """
        return self.is_close_to_some_site(3, 3)

    @hybrid_property
    def is_ptm_distal(self):
        """Check if the mutation is distal flanking mutation of some PTM site.

        Distal flank is defined here as [pos - 7, pos + 7] span,
        where pos is the position of a PTM site.
        """
        return self.is_close_to_some_site(7, 7)

    @hybrid_property
    def cnt_ptm_affected(self):
        """How many PTM sites might be affected by this mutation,

        when taking into account -7 to +7 spans of each PTM site.
        """
        sites = Protein.query.get(self.protein_id).sites
        pos = self.position
        a = 0
        b = len(sites)

        cnt_affected = 0
        hit = None

        while a != b:
            p = (b - a) // 2 + a
            site_pos = sites[p].position
            if site_pos - 7 <= pos and pos <= site_pos + 7:
                hit = p
                cnt_affected += 1
                break
            if pos > site_pos:
                a = p + 1
            else:
                b = p
        else:
            return 0

        def cond():
            try:
                site_pos = sites[p].position
                return site_pos - 7 <= pos and pos <= site_pos + 7
            except IndexError:
                return False

        # go to right from found site, check if there is more overlappig sites
        p = hit + 1
        while cond():
            cnt_affected += 1
            p += 1

        # and then go to the left
        p = hit - 1
        while cond():
            cnt_affected += 1
            p -= 1

        return cnt_affected

    @cnt_ptm_affected.expression
    def cnt_ptm_affected(self):
        """SQL expression for cnt_ptm_affected"""
        pos = self.position
        count = db.session.query(func.count(Site.id)).\
            filter_by(protein_id=self.protein_id).\
            filter(Site.position.between(pos - 8, pos + 8)).scalar()

        return count

    @hybrid_property
    def impact_on_ptm(self):
        """How intense might be impact of the mutation on the closest PTM site.

        Possible values are: 'direct', 'proximal', or 'diastal'. Those
        properties are based on the distance measurement to closest PTM site
        """
        if self.is_ptm_direct:
            return 'direct'
        if self.is_ptm_proximal:
            return 'proximal'
        if self.is_ptm_distal:
            return 'distal'
        return None

    @hybrid_method
    def is_close_to_some_site(self, left, right):
        """Check if the mutation lies close to any of sites.

        Arguments define span around each site to be checked:
        (site_pos - left, site_pos + right)
        site_pos is the position of a site

        Algoritm is based on bisection and an assumption,
        that sites are sorted by position in the database.
        """
        sites = Protein.query.get(self.protein_id).sites
        pos = self.position
        a = 0
        b = len(sites)
        while a != b:
            p = (b - a) // 2 + a
            site_pos = sites[p].position
            if site_pos - left <= pos and pos <= site_pos + right:
                return True
            if pos > site_pos:
                a = p + 1
            else:
                b = p
        return False

    @is_close_to_some_site.expression
    def is_close_to_some_site(self, left, right):
        """SQL expression for is_close_to_some_site"""
        position = self.position
        q = exists().where(
            and_(
                Site.protein_id == self.protein_id,
                Site.position.between(position - left, position + right)
                )
        )
        return db.session.query(q).scalar()
