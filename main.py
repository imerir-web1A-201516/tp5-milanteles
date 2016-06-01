# -*- coding: utf-8 -*-
from flask import Flask, request, make_response
import json, os, psycopg2, urlparse

app = Flask(__name__)
app.debug = True

##################################################################

def db_init():
    """Cette fonction crée la connexion à la base de données et renvoie,
       l'objet de connexion et un curseur."""
    
    urlparse.uses_netloc.append("postgres")
    url = urlparse.urlparse(os.environ["DATABASE_URL"])
    
    conn = psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    cur = conn.cursor()    
    return conn, cur
      
def db_createTables(conn, cur):
  """Cette fonction initialise la base de données. Elle est invoquée par
     un chemin spécial - voir /debug/db/reset"""
  
  cur.execute('''\
    DROP TABLE IF EXISTS Product;
    CREATE TABLE Product (
      pid SERIAL,
      name varchar,
      price float
    );
    INSERT INTO Product (name, price) VALUES ('Pomme', 1.20);
    INSERT INTO Product (name, price) VALUES ('Poire', 1.60);
    INSERT INTO Product (name, price) VALUES ('Fraise', 3.80);
    DROP TABLE IF EXISTS Basket;
    CREATE TABLE Basket (
      bid SERIAL,
      basket_uid INT
    );
    DROP TABLE IF EXISTS BasketContent;
    CREATE TABLE BasketContent (
      basket_ref INT,
      product_ref INT,
      product_qt INT
    );
    DROP TABLE IF EXISTS UserAccount;
    CREATE TABLE UserAccount (
      uid SERIAL,
      email varchar,
      password varchar
    );
    INSERT INTO UserAccount (email, password) VALUES ('pierre', '123456');
    INSERT INTO UserAccount (email, password) VALUES ('toto', 'babar');
    ''')
  conn.commit()

def db_select(cur, sql, params = None):
  """Cette fonction exécute une requête SQL de type SELECT
     et renvoie le résultat avec pour chaque ligne un dictionnaire
     liant les noms de colonnes aux données."""
  
  if params:
    cur.execute(sql, params)
  else:
    cur.execute(sql)
  
  rows = cur.fetchall()
  cleanRows = []
  if rows != None:
    columns = map(lambda d: d[0], cur.description)
    for row in rows:
      cleanRow = dict()
      for (i,colName) in enumerate(columns):
        cleanRow[colName] = row[i]
      cleanRows.append(cleanRow)
  
  return cleanRows

##################################################################

@app.route('/debug/db/reset')
def route_dbinit():
  """Cette route sert à initialiser (ou nettoyer) la base de données."""
  
  conn, cur = db_init()
  db_createTables(conn, cur)
  conn.close()
  return "Done."

#-----------------------------------------------------------------

@app.route('/products')
def products_fetchall():
  """Exemple d'une requête qui exécute une requête SQL et renvoie
     le résultat."""
  
  conn, cur = db_init()
  result = db_select(cur, 'SELECT * FROM Product')
  conn.close()
  
  resp = make_response(json.dumps(result))
  resp.mimetype = 'application/json'
  return resp

#-----------------------------------------------------------------

@app.route('/products', methods=['POST'])
def products_add():
  data = request.get_json()
  
  conn, cur = db_init()
  cur.execute('INSERT INTO Product (name, price) VALUES (%(name)s, %(price)s)', {
    'name': data["name"],
    'price': data["price"]
  })
  conn.commit()
  conn.close()
  
  resp = make_response('"OK"', 201)
  resp.mimetype = 'application/json'
  return resp

#-----------------------------------------------------------------

@app.route('/products/<int:pid>')
def products_fetchone(pid):
  conn, cur = db_init()
  result = db_select(cur, 'SELECT * FROM Product WHERE pid = %(pid)s', {
    'pid': pid
  })
  conn.close()
  
  if len(result) != 1:
    return make_response("Not found", 404)
  
  resp = make_response(json.dumps(result[0]))
  resp.mimetype = 'application/json'
  return resp

#-----------------------------------------------------------------

@app.route('/baskets')
def basket_fetchall():
  conn, cur = db_init()
  result = db_select(cur, 'SELECT bid, email, uid FROM Basket JOIN UserAccount ON uid = basket_uid')
  conn.close()
  
  resp = make_response(json.dumps(result))
  resp.mimetype = 'application/json'
  return resp
  
#-----------------------------------------------------------------

@app.route('/baskets/create', methods=['GET'])
@app.route('/baskets', methods=['POST'])
def basket_create():
  conn, cur = db_init()
  
  if not(request.authorization):
    resp = make_response("Credentials required", 401)
    resp.headers['WWW-Authenticate'] = 'Basic realm="Credentials required"'
    return resp
  
  result = db_select(cur, 'SELECT uid FROM UserAccount WHERE email = %(e)s AND password = %(p)s', {
    'e': request.authorization.username,
    'p': request.authorization.password
  })
  
  if len(result) != 1:
    resp = make_response("Invalid credentials", 401)
    resp.headers['WWW-Authenticate'] = 'Basic realm="Credentials required"'
    return resp
  
  uid = result[0]['uid']
  
  cur.execute('INSERT INTO basket (basket_uid) VALUES (%(uid)s)', {
    'uid': uid
  })
  conn.commit()
  bid = cur.lastrowid
  
  conn.close()

  resp = make_response("OK", 201)
  resp.headers['Location'] = '/baskets/%d' % bid
  return resp

#-----------------------------------------------------------------

@app.route('/baskets/<int:bid>', methods=['POST'])
def basket_insertintoone(bid):
  conn, cur = db_init()
  
  if not(request.authorization):
    resp = make_response("Credentials required", 401)
    resp.headers['WWW-Authenticate'] = 'Basic realm="Credentials required"'
    return resp
  
  result = db_select(cur, 'SELECT uid FROM UserAccount WHERE email = %(e)s AND password = %(p)s', {
    'e': request.authorization.username,
    'p': request.authorization.password
  })
  
  if len(result) != 1:
    resp = make_response("Invalid credentials", 401)
    resp.headers['WWW-Authenticate'] = 'Basic realm="Credentials required"'
    return resp
  
  uid = result[0]['uid']
  
  # validate bid
  
  result = db_select(cur, 'SELECT bid FROM Basket WHERE bid = %(bid)s AND basket_uid = %(uid)s', {
    'bid': bid,
    'uid': uid
  })
  
  if len(result) != 1:
    resp = make_response("No such basket", 404)
    return resp
  
  # read post data
  
  try:
    pref = int(request.form['product_ref'])
    pqt  = int(request.form['product_qt'])
    
    result = db_select(cur, 'SELECT 1 FROM Product WHERE pid = %(pid)s', {
      'pid': pref
    })
    if len(result) != 1:
      resp = make_response("No such product", 404)
      return resp
    
    if pqt <= 0:
      raise ValueError('product_qt must be greater than 0')
  except:
    resp = make_response("Missing proper product_ref/product_qt", 400)
    return resp

  cur.execute('INSERT INTO BasketContent (basket_ref, product_ref) VALUES (%(bid)s, %(pid)s)', {
    'bid': bid,
    'pid': pref
  })
  conn.commit()
  conn.close()

  resp = make_response("OK", 201)
  return resp

if __name__ == "__main__":
  app.debug = True
  app.run()
