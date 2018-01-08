import gzip
from tempfile import TemporaryDirectory

from database import db
from database_testing import DatabaseTest
from imports.sites.elm import PhosphoELMImporter
from miscellaneous import make_named_gz_file, make_named_temp_file
from models import Protein


MAPPINGS = """\
P62753	RefSeq_NT	NM_001010.2
"""


CANONICAL = """\
>sp|P62753|RS6_HUMAN 40S ribosomal protein S6 OS=Homo sapiens GN=RPS6 PE=1 SV=1
MKLNISFPATGCQKLIEVDDERKLRTFYEKRMATEVAADALGEEWKGYVVRISGGNDKQG
FPMKQGVLTHGRVRLLLSKGHSCYRPRRTGERKRKSVRGCIVDANLSVLNLVIVKKGEKD
IPGLTDTTVPRRLGPKRASRIRKLFNLSKEDDVRQYVVRKPLNKEGKKPRTKAPKIQRLV
TPRVLQHKRRRIALKKQRTKKNKEEAAEYAKLLAKRMKEAKEKRQEQIAKRRRLSSLRAS
TSKSESSQK
"""

ALTERNATIVE = ''


# just a combination
SITES = """\
acc	sequence	position	code	pmids	kinases	source	species	entry_date
P62753	MKLNISFPATGCQKLIEVDDERKLRTFYEKRMATEVAADALGEEWKGYVVRISGGNDKQGFPMKQGVLTHGRVRLLLSKGHSCYRPRRTGERKRKSVRGCIVDANLSVLNLVIVKKGEKDIPGLTDTTVPRRLGPKRASRIRKLFNLSKEDDVRQYVVRKPLNKEGKKPRTKAPKIQRLVTPRVLQHKRRRIALKKQRTKKNKEEAAEYAKLLAKRMKEAKEKRQEQIAKRRRLSSLRASTSKSESSQK	236	S	17360704	RSK_group	LTP	Homo sapiens	2004-12-31 00:00:00+01
P62753	MKLNISFPATGCQKLIEVDDERKLRTFYEKRMATEVAADALGEEWKGYVVRISGGNDKQGFPMKQGVLTHGRVRLLLSKGHSCYRPRRTGERKRKSVRGCIVDANLSVLNLVIVKKGEKDIPGLTDTTVPRRLGPKRASRIRKLFNLSKEDDVRQYVVRKPLNKEGKKPRTKAPKIQRLVTPRVLQHKRRRIALKKQRTKKNKEEAAEYAKLLAKRMKEAKEKRQEQIAKRRRLSSLRASTSKSESSQK	236	S	17360704	p70S6K	LTP	Homo sapiens	2004-12-31 00:00:00+01
P62753	MKLNISFPATGCQKLIEVDDERKLRTFYEKRMATEVAADALGEEWKGYVVRISGGNDKQGFPMKQGVLTHGRVRLLLSKGHSCYRPRRTGERKRKSVRGCIVDANLSVLNLVIVKKGEKDIPGLTDTTVPRRLGPKRASRIRKLFNLSKEDDVRQYVVRKPLNKEGKKPRTKAPKIQRLVTPRVLQHKRRRIALKKQRTKKNKEEAAEYAKLLAKRMKEAKEKRQEQIAKRRRLSSLRASTSKSESSQK	242	S	18669648		HTP	Homo sapiens	2004-12-31 00:00:00+01
P62753	MKLNISFPATGCQKLIEVDDERKLRTFYEKRMATEVAADALGEEWKGYVVRISGGNDKQGFPMKQGVLTHGRVRLLLSKGHSCYRPRRTGERKRKSVRGCIVDANLSVLNLVIVKKGEKDIPGLTDTTVPRRLGPKRASRIRKLFNLSKEDDVRQYVVRKPLNKEGKKPRTKAPKIQRLVTPRVLQHKRRRIALKKQRTKKNKEEAAEYAKLLAKRMKEAKEKRQEQIAKRRRLSSLRASTSKSESSQK	242	S	N.N.		LTP	Homo sapiens	2004-12-31 00:00:00+01
"""


class TestImport(DatabaseTest):

    def test_import(self):
        protein = Protein(
            refseq='NM_001010',
            sequence='MKLNISFPATGCQKLIEVDDERKLRTFYEKRMATEVAADALGEEWKGYVVRISGGNDKQGFPMKQGVLTHGRVRLLLSKGHSCYRPRRTGERKRKSVRGCIVDANLSVLNLVIVKKGEKDIPGLTDTTVPRRLGPKRASRIRKLFNLSKEDDVRQYVVRKPLNKEGKKPRTKAPKIQRLVTPRVLQHKRRRIALKKQRTKKNKEEAAEYAKLLAKRMKEAKEKRQEQIAKRRRLSSLRASTSKSESSQK*'
        )

        db.session.add(protein)

        with TemporaryDirectory() as dir_path:

            with gzip.open(dir_path + '/O-GalNAc_site_dataset.gz', 'wt') as f:
                f.write(SITES)

            importer = PhosphoELMImporter(
                make_named_gz_file(CANONICAL),
                make_named_gz_file(ALTERNATIVE),
                make_named_gz_file(MAPPINGS)
            )

            sites = importer.load_sites(make_named_temp_file(SITES))

            assert len(sites) == 2

            sites_by_pos = {site.position: site for site in sites}

            assert sites_by_pos[236].residue == sites_by_pos[242].residue == 'S'
            assert sites_by_pos[236].type == sites_by_pos[242].type == {'phosphorylation'}

            assert sites_by_pos[236].pmid == {'17360704'}
