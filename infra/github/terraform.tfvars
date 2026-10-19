project = "njoaguof-api"
# gh api repos/tor-gu/njoaguof-api/actions/oidc/customization/sub
github_subject_prefix = "repo:tor-gu@99346055/njoaguof-api@1424958506"

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
