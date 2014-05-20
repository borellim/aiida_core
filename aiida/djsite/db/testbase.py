"""
Base class for AiiDA tests
"""
from django.utils import unittest

# Add a new entry here if you add a file with tests under aiida.djsite.db.subtests
# The key is the name to use in the 'verdi test' command (e.g., a key 'generic'
# can be run using 'verdi test db.generic')
# The value must be the module name containing the subclasses of unittest.TestCase
db_test_list = {
    'generic': 'aiida.djsite.db.subtests.generic',
    'nodes': 'aiida.djsite.db.subtests.nodes',
    'dataclasses': 'aiida.djsite.db.subtests.dataclasses',
    'qepw': 'aiida.djsite.db.subtests.quantumespressopw'}

class AiidaTestCase(unittest.TestCase):
    """
    Automatically takes care of the setUpClass and TearDownClass, when needed.
    """
    @classmethod
    def setUpClass(cls):
        import getpass
        from aiida.djsite.db.models import DbUser
        from aiida.orm import Computer
        from aiida.djsite.utils import get_configured_user_email

        cls.user = DbUser.objects.create_user(get_configured_user_email(),
                                              'fakepwd')
        cls.computer = Computer(name='localhost',
                                hostname='localhost',
                                transport_type='ssh',
                                scheduler_type='pbspro',
                                workdir='/tmp/aiida')
        cls.computer.store()

    @classmethod
    def tearDownClass(cls):
        import getpass
        from django.core.exceptions import ObjectDoesNotExist
        from aiida.djsite.db.models import DbComputer, DbUser
        from aiida.djsite.utils import get_configured_user_email

        # I first delete the workflows
        from aiida.djsite.db.models import DbWorkflow
        DbWorkflow.objects.all().delete()

        # Delete groups
        from aiida.djsite.db.models import DbGroup
        DbGroup.objects.all().delete()

        # I first need to delete the links, because in principle I could
        # not delete input nodes, only outputs. For simplicity, since
        # I am deleting everything, I delete the links first
        from aiida.djsite.db.models import DbLink
        DbLink.objects.all().delete()
        
        # Then I delete the nodes, otherwise I cannot
        # delete computers and users
        from aiida.djsite.db.models import DbNode
        DbNode.objects.all().delete()

        try:
            DbUser.objects.get(email=get_configured_user_email()).delete()
        except ObjectDoesNotExist:
            pass
        
        DbComputer.objects.all().delete()
