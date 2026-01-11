
locals {
  s3_buckets = {
    host = {
      name          = "${var.project}-host"
      website       = true
      public_access = true
    }

    reporting = {
      name          = "${var.project}-reportes-output"
      website       = false
      public_access = false
      lifecycle_days = 30
    }

    scripts = {
      name          = "${var.project}-glue-scripts"
      website       = false
      public_access = false
    }
  }
}

/*
  dynamo_tables_list_name = {
    table_lock   = "${var.project}-state-locking"
    table_result = "${var.project}-result-table-aws"
  }
 */ 

