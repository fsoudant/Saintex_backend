import Foundation

enum ErreurServeur: Error, CustomStringConvertible {
    case http(Int)
    case reponseVide

    var description: String {
        switch self {
        case .http(let code): return "HTTP \(code)"
        case .reponseVide: return "réponse vide"
        }
    }
}

/// Client de POST /api/cache/ (clients.views.CacheView) : le contact du
/// téléphone avec le serveur. Aucune position n'est envoyée.
final class SaintexServer {
    // TODO : à externaliser (environnements) — même URL que mobile/src/api.ts.
    private let url = URL(string: "https://saintex.myddns.me/api/cache/")!

    /// `fin` est appelé sur une file d'arrière-plan.
    func contacter(
        _ requete: ContactRequest,
        jeton: String,
        fin: @escaping (Result<ContactResponse, Error>) -> Void
    ) {
        var demande = URLRequest(url: url)
        demande.httpMethod = "POST"
        demande.timeoutInterval = 30
        demande.setValue("application/json", forHTTPHeaderField: "Content-Type")
        demande.setValue("Bearer \(jeton)", forHTTPHeaderField: "Authorization")
        do {
            demande.httpBody = try JSONEncoder().encode(requete)
        } catch {
            fin(.failure(error))
            return
        }

        URLSession.shared.dataTask(with: demande) { data, reponse, erreur in
            if let erreur = erreur {
                fin(.failure(erreur))
                return
            }
            if let http = reponse as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                fin(.failure(ErreurServeur.http(http.statusCode)))
                return
            }
            guard let data = data else {
                fin(.failure(ErreurServeur.reponseVide))
                return
            }
            do {
                fin(.success(try JSONDecoder().decode(ContactResponse.self, from: data)))
            } catch {
                fin(.failure(error))
            }
        }.resume()
    }
}
