// Node resolve hook: @material/material-color-utilities ships ESM with
// extensionless relative imports, which Node refuses. Retry them with ".js".
import { registerHooks } from "node:module";

registerHooks({
  resolve(specifier, context, next) {
    try {
      return next(specifier, context);
    } catch (err) {
      if (specifier.startsWith(".") && !specifier.endsWith(".js")) {
        return next(specifier + ".js", context);
      }
      throw err;
    }
  },
});
