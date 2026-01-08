
locals {
  s3_list_name = {
    bucket_host    = "${var.project}-host-s3-control-financiero"
  }
/*
  dynamo_tables_list_name = {
    table_lock   = "${var.project}-state-locking"
    table_result = "${var.project}-result-table-aws"
  }
 */ 
}
