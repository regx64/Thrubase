; Thrubase · Python queries
; Capture names are the contract with adapters/python/__init__.py (PythonAdapter.extract).

; ---- definitions ------------------------------------------------------------
(function_definition
  name: (identifier) @def.name
  parameters: (parameters) @def.params
  return_type: (_)? @def.returns) @def.function

(class_definition
  name: (identifier) @def.name
  superclasses: (argument_list)? @def.bases) @def.class

; ---- typed names (parameters are read from @def.params) -------------------
(assignment
  left: (_) @bind.left
  type: (_)? @bind.type
  right: (_)? @bind.right) @bind

; ---- imports ----------------------------------------------------------------
(import_statement) @import

(import_from_statement) @import.from

; ---- calls ------------------------------------------------------------------
(call
  function: (_) @call.callee
  arguments: (_) @call.args) @call

; ---- comments (left out of body hashes) ------------------------------------
(comment) @comment

; ---- meaningful spots (locate checkpoints) ----------------------------------
(raise_statement) @spot.raise

(except_clause) @spot.except

(return_statement) @spot.return

; ---- entry points -----------------------------------------------------------
(module
  (if_statement
    condition: (comparison_operator) @main.cond) @main.block)

; module-level assignments: `app = Flask(__name__)`, `urlpatterns = [...]`
(module
  (expression_statement
    (assignment
      left: (identifier) @assign.name
      right: (_) @assign.value)))
