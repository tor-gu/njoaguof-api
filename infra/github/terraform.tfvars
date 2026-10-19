project     = "njoaguof-api"
github_repo = "tor-gu/njoaguof-api"

envs = {
  dev = {
    stack_name = "NjoaguofApiDev"
  }
  prod = {
    stack_name = "NjoaguofApi"
  }
}

cfn_execution_role_arn = "arn:aws:iam::490461464130:role/aws-sam-cli-managed-prod-CloudFormationExecutionR-Q7T0TM3BM99D"
sam_artifact_bucket    = "aws-sam-cli-managed-prod-pipeline-artifactsbucket-lshck0q70sdj"
torguapi_layer_name    = "layer_torguapi"
