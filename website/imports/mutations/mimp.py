from warnings import warn

from models import MIMPMutation, SiteType
from helpers.bioinf import decode_raw_mutation
from helpers.parsers import tsv_file_iterator

from .mutation_importer import MutationImporter


class MIMPImporter(MutationImporter):
    # load("all_mimp_annotations_p085.rsav")
    # write.table(all_mimp_annotations, file="all_mimp_annotations.tsv",
    # row.names=F, quote=F, sep='\t')

    name = 'mimp'
    model = MIMPMutation
    default_path = 'data/mutations/all_mimp_annotations.tsv'
    header = [
        'gene', 'mut', 'psite_pos', 'mut_dist', 'wt', 'mt', 'score_wt',
        'score_mt', 'log_ratio', 'pwm', 'pwm_fam', 'nseqs', 'prob', 'effect'
    ]
    insert_keys = (
        'mutation_id',
        'position_in_motif',
        'effect',
        'pwm',
        'pwm_family',
        'probability',
        'site_id'
    )
    site_type = 'phosphorylation'

    def iterate_lines(self, path):
        return tsv_file_iterator(path, self.header)

    def parse(self, path):
        mimps = []
        site_type = SiteType.query.filter_by(name=self.site_type).one()

        def parser(line):
            nonlocal mimps

            refseq = line[0]
            mut = line[1]
            psite_pos = line[2]

            try:
                protein = self.proteins[refseq]
            except KeyError:
                return

            ref, pos, alt = decode_raw_mutation(mut)

            try:
                assert ref == protein.sequence[pos - 1]
            except (AssertionError, IndexError):
                self.broken_seq[refseq].append((protein.id, alt))
                return

            assert line[13] in ('gain', 'loss')

            # MIMP mutations are always hardcoded PTM mutations
            mutation_id = self.get_or_make_mutation(pos, protein.id, alt, True)

            psite_pos = int(psite_pos)

            affected_sites = [
                site
                for site in protein.sites
                if site.position == psite_pos
                and any(t == site_type for t in site.types)
            ]

            # as this is site-type specific and only one site object of given type should be placed at a position,
            # we can should assume that the selection above will always produce less than two sites
            assert len(affected_sites) <= 1

            if not affected_sites:
                warning = UserWarning(
                    f'Skipping {refseq}: {ref}{pos}{alt} (for site at position {psite_pos}): '
                    'MIMP site does not match to the database - given site not found.'
                )
                print(warning)
                warn(warning)
                return

            site_id = affected_sites[0].id

            mimps.append(
                (
                    mutation_id,
                    int(line[3]),
                    1 if line[13] == 'gain' else 0,
                    line[9],
                    line[10],
                    float(line[12]),
                    site_id
                )
            )

        for line in self.iterate_lines(path):
            parser(line)

        return mimps

    def insert_details(self, mimps):

        self.insert_list(mimps)
