# -*- coding: utf-8 -*-

# Automatic provisioning of AWS SQS queues.

import time
import boto.sqs
import charon.util
import charon.resources
import charon.ec2_utils


class SQSQueueDefinition(charon.resources.ResourceDefinition):
    """Definition of an SQS queue."""

    @classmethod
    def get_type(cls):
        return "sqs-queue"

    def __init__(self, xml):
        charon.resources.ResourceDefinition.__init__(self, xml)
        self.queue_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")


class SQSQueueState(charon.resources.ResourceState):
    """State of an SQS queue."""

    state = charon.util.attr_property("state", charon.resources.ResourceState.MISSING, int)
    queue_name = charon.util.attr_property("ec2.queueName", None)
    access_key_id = charon.util.attr_property("ec2.accessKeyId", None)
    region = charon.util.attr_property("ec2.region", None)


    @classmethod
    def get_type(cls):
        return "sqs-queue"


    def __init__(self, depl, name, id):
        charon.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None


    def show_type(self):
        s = super(SQSQueueState, self).show_type()
        if self.region: s= "{0} [{1}]".format(s, self.region)
        return s


    def connect(self):
        if self._conn: return
        assert self.region
        (access_key_id, secret_access_key) = charon.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._conn = boto.sqs.connect_to_region(
            region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)


    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        q = self._conn.lookup(self.queue_name)
        if q:
            self.log("destroying queue ‘{0}’...".format(self.queue_name))
            self._conn.delete_queue(q)
        with self.depl._db:
            self.state = self.MISSING
            self.queue_name = None
            self.region = None
            self.access_key_id = None


    def create(self, defn, check, allow_reboot):

        self.access_key_id = defn.access_key_id or charon.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        if self.state == self.UP and (self.queue_name != defn.queue_name or self.region != defn.region):
            self.log("queue definition changed, recreating...")
            self._destroy()
            self._conn = None # necessary if region changed

        if check or self.state != self.UP:

            self.region = defn.region
            self.connect()

            q = self._conn.lookup(defn.queue_name)

            if not q or self.state != self.UP:
                if q:
                    # SQS requires us to wait for 60 seconds to
                    # recreate a queue.
                    self.log("deleting queue ‘{0}’ (and waiting 60 seconds)...".format(defn.queue_name))
                    self._conn.delete_queue(q)
                    time.sleep(61)
                self.log("creating SQS queue ‘{0}’...".format(defn.queue_name))
                self._conn.create_queue(defn.queue_name)
                # FIXME: retry if we get QueueDeletedRecently

            with self.depl._db:
                self.state = self.UP
                self.queue_name = defn.queue_name


    def destroy(self):
        self._destroy()
        return True
