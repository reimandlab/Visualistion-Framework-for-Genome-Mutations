import os
from collections import OrderedDict
from tqdm import tqdm
from models import Gene
from models import Site
from helpers.commands import register_decorator


EXPORTERS = OrderedDict()
exporter = register_decorator(EXPORTERS)


def create_path_if_possible(path):
    """Create all directories on way to the file specified in given path.
    Does not raise any errors if the path already exists."""
    return os.makedirs(os.path.dirname(path), exist_ok=True)


@exporter
def sequences_ac(path='exported/preferred_isoforms_sequences.fa'):
    """Sequences as needed for Active Driver input.
    Includes only data from primary (preferred) isoforms."""

    create_path_if_possible(path)

    with open(path, 'w') as f:
        for gene in tqdm(Gene.query.all()):
            if not gene.preferred_isoform:
                continue
            f.write('>' + gene.name + '\n')
            f.write(gene.preferred_isoform.sequence + '\n')

    return path


@exporter
def disorder_ac(path='exported/preferred_isoforms_disorder.fa'):
    """Disorder data as needed for Active Driver input.
    Includes only data from primary (preferred) isoforms."""

    create_path_if_possible(path)

    with open(path, 'w') as f:
        for gene in tqdm(Gene.query.all()):
            if not gene.preferred_isoform:
                continue
            f.write('>' + gene.name + '\n')
            f.write(gene.preferred_isoform.disorder_map + '\n')

    return path


@exporter
def sites_ac(path='exported/sites.tsv'):
    """Sites as needed for Active Driver input.
    Includes only data from primary (preferred) isoforms."""
    header = ['gene', 'position', 'residue', 'kinase', 'pmid']

    create_path_if_possible(path)

    with open(path, 'w') as f:
        f.write('\t'.join(header) + '\n')
        for site in tqdm(Site.query.all()):
            if not site.protein or not site.protein.is_preferred_isoform:
                continue
            data = [
                site.protein.gene.name, str(site.position), site.residue,
                ','.join([k.name for k in site.kinases]),
                site.pmid
            ]

            f.write('\t'.join(data) + '\n')

    return path

