// Sends Traktor's deck info to GOOD MIXX. Both addresses are tried, so the standalone
// GOOD MIXX app (8770) and the one built into Crate OS (18770) can both follow Traktor.
var API_BASE_URLS = ["http://localhost:8770/traktor", "http://localhost:18770/traktor"]

function send(endpoint, data) {
  var body = JSON.stringify(data)
  for (var i = 0; i < API_BASE_URLS.length; i++) {
    var request = new XMLHttpRequest()
    request.open("POST", API_BASE_URLS[i] + "/" + endpoint, true)
    request.setRequestHeader("Content-Type", "application/json")
    request.setRequestHeader("Content-Length", body.length)
    request.send(body)
  }
}
