resource "aws_lambda_function" "mcp" {
  function_name = "bookshelf-mcp"
  runtime       = "nodejs24.x"
  handler       = "handler.handler"
  memory_size   = 1024
}
