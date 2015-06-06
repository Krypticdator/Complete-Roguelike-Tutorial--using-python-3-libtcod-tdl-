__author__ = 'Toni'

import tdl
from random import randint
import math

SCREEN_WIDTH = 80
SCREEN_HEIGHT = 65

MAX_ROOM_MONSTERS = 3

#size of the map
MAP_WIDTH = 80
MAP_HEIGHT = 50

#sizes and coordinates relevant for the GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT

LIMIT_FPS = 20
playerX = SCREEN_WIDTH/2
playerY = SCREEN_HEIGHT/2

console = tdl.init(SCREEN_WIDTH, SCREEN_HEIGHT, title = "Roguelike")
panel = tdl.Console(SCREEN_WIDTH, PANEL_HEIGHT)
con = tdl.Console(MAP_WIDTH, MAP_HEIGHT)
tdl.setFPS(LIMIT_FPS)

ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30

fov_recompute = False

FOV_ALGO = 0  #default FOV algorithm
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10

color_dark_wall = [0, 0, 100]
color_light_wall = [130, 110, 50]
color_dark_ground = [50, 50, 150]
color_light_ground = [200, 180, 50]
color_yellow = [255, 255, 0]
color_green = [0, 255, 0]
color_dark_green = [0, 153, 0]
color_dark_red = [204, 0, 0]

game_state = 'playing'
player_action = None

class Tile:
    #a tile of the map and its properties
    def __init__(self, blocked, block_sight = None):
        self.blocked = blocked

        #all tiles start unexplored
        self.explored = False

        #by default, if a tile is blocked, it also blocks sight
        if block_sight is None: block_sight = blocked
        self.block_sight = block_sight

class Rect:
    #a rectangle on the map. used to characterize a room.
    def __init__(self, x, y, w, h):
        self.x1 = x
        self.y1 = y
        self.x2 = x + w
        self.y2 = y + h

    def center(self):
        center_x = int((self.x1 + self.x2) / 2)
        center_y = int((self.y1 + self.y2) / 2)
        return (center_x, center_y)

    def intersect(self, other):
        #returns true if this rectangle intersects with another one
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and
                self.y1 <= other.y2 and self.y2 >= other.y1)


class Fighter:
    #combat-related properties and methods (monster, player, NPC).
    def __init__(self, hp, defense, power, death_function=None):
        self.max_hp = hp
        self.hp = hp
        self.defense = defense
        self.power = power
        self.death_function = death_function

    def take_damage(self, damage):
        #apply damage if possible
        if damage > 0:
            self.hp -= damage
        if self.hp <= 0:
            function = self.death_function
            if function is not None:
                function(self.owner)

    def attack(self, target):
        #a simple formula for attack damage
        damage = self.power - target.fighter.defense

        if damage > 0:
            #make the target take some damage
            print (self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points.')
            target.fighter.take_damage(damage)
        else:
            print (self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect!')

class BasicMonster:
    #AI for a basic monster.
    def take_turn(self):
        global visible_tiles
        #a basic monster takes its turn. If you can see it, it can see you
        monster = self.owner
        #if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
        coord = (monster.x, monster.y)
        if coord in visible_tiles:

            #move towards player if far away
            if monster.distance_to(player) >= 2:
                monster.move_towards(player.x, player.y)

            #close enough, attack! (if the player is still alive.)
            elif player.fighter.hp > 0:
                monster.fighter.attack(player)

class GameObject:
    # this is a generic object: the player, a monster, an item, the stairs...
    # it's always represented by a character on screen.
    def __init__(self, x, y, char, name, color, blocks=False, fighter=None, ai=None):
        self.name = name
        self.blocks = blocks
        self.x = x
        self.y = y
        self.char = char
        self.color = color

        self.fighter = fighter
        if self.fighter:  #let the fighter component know who owns it
            self.fighter.owner = self

        self.ai = ai
        if self.ai:  #let the AI component know who owns it
            self.ai.owner = self

    def move(self, dx, dy):
        #move by the given amount, if the destination is not blocked
        if not is_blocked(self.x + dx, self.y + dy):
            self.x += dx
            self.y += dy
            #print(str(self.x) + " " + str(self.y))

    def move_towards(self, target_x, target_y):
        #vector from this object to the target, and distance
        dx = target_x - self.x
        dy = target_y - self.y
        distance = math.sqrt(dx ** 2 + dy ** 2)

        #normalize it to length 1 (preserving direction), then round it and
        #convert to integer so the movement is restricted to the map grid
        dx = int(round(dx / distance))
        dy = int(round(dy / distance))
        self.move(dx, dy)

    def distance_to(self, other):
        #return the distance to another object
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx ** 2 + dy ** 2)

    def draw(self):
        global visible_tiles
        coord = (self.x, self.y)
        if coord in visible_tiles:
            con.drawChar(self.x, self.y, self.char, self.color)

    def clear(self):
        con.drawChar(self.x, self.y, ' ')

    def send_to_back(self):
        #make this object be drawn first, so all others appear above it if they're in the same tile.
        global objects
        objects.remove(self)
        objects.insert(0, self)



def create_room(room):
    global map
    #go through the tiles in the rectangle and make them passable
    for x in range(room.x1 + 1, room.x2):
        for y in range(room.y1 + 1, room.y2):
            map[x][y].blocked = False
            map[x][y].block_sight = False

def is_blocked(x, y):
    global map
    #first test the map tile
    if map[x][y].blocked:
        return True

    #now check for any blocking objects
    for object in objects:
        if object.blocks and object.x == x and object.y == y:
            return True

    return False

def place_objects(room):
    num_monsters = randint(0, MAX_ROOM_MONSTERS)

    for i in range(num_monsters):
        #choose random spot for this monster
        x = randint(room.x1, room.x2)
        y = randint(room.y1, room.y2)

        #only place it if the tile is not blocked
        if not is_blocked(x, y):
            if randint(0, 100) < 80:
                fighter_component = Fighter(hp=10, defense=0, power=3, death_function=monster_death)
                ai_component = BasicMonster()
                monster = GameObject(x, y, 'o', 'orc', color_green, blocks=True, fighter=fighter_component, ai=ai_component)
            else:
                fighter_component = Fighter(hp=16, defense=1, power=4, death_function=monster_death)
                ai_component = BasicMonster()
                monster = GameObject(x, y, 'I', 'troll', color_dark_green, blocks=True, fighter=fighter_component, ai=ai_component)

            objects.append(monster)

def create_h_tunnel(x1, x2, y):
    global map
    x1 = int(x1)
    x2 = int(x2)
    y = int(y)
    for x in range(min(x1, x2), max(x1, x2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False

def create_v_tunnel(y1, y2, x):
    global map
    y1 = int(y1)
    y2 = int(y2)
    x = int(x)
    #vertical tunnel
    for y in range(min(y1, y2), max(y1, y2) + 1):
        map[x][y].blocked = False
        map[x][y].block_sight = False

def is_visible_tile(x, y):
    global map
    x = int(x)
    y = int(y)
    #print(str(map))
    if x >= MAP_WIDTH or x < 0:
        return False
    elif y >= MAP_HEIGHT or y < 0:
        return False
    elif map[x][y].blocked == True:
        return False
    elif map[x][y].block_sight == True:
        return False
    else:
        return True

def make_map():
    global map, player, visible_tiles

    #fill map with "unblocked" tiles
    map = [[ Tile(True)
        for y in range(MAP_HEIGHT) ]
            for x in range(MAP_WIDTH) ]



    rooms = []
    num_rooms = 0

    for r in range(MAX_ROOMS):
        #random width and height
        w = randint(ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        h = randint(ROOM_MIN_SIZE, ROOM_MAX_SIZE)
        #random position without going out of the boundaries of the map
        x = randint(0, MAP_WIDTH - w -1)
        y = randint(0, MAP_HEIGHT - h -1)
        x = int(x)
        y = int(y)
        #"Rect" class makes rectangles easier to work with
        new_room = Rect(x, y, w, h)

        #run through the other rooms and see if they intersect with this one
        failed = False
        for other_room in rooms:
            if new_room.intersect(other_room):
                failed = True
                break

        if not failed:
            #this means there are no intersections, so this room is valid

            #"paint" it to the map's tiles
            create_room(new_room)

            #add some contents to this room, such as monsters
            place_objects(new_room)

            #center coordinates of new room, will be useful later
            (new_x, new_y) = new_room.center()

            if num_rooms == 0:
                #this is the first room, where the player starts at
                player.x = new_x
                player.y = new_y
                visible_tiles = tdl.map.quickFOV(new_x, new_y, is_visible_tile)
                #print(visible_tiles)
            else:
                #all rooms after the first:
                #connect it to the previous room with a tunnel

                #center coordinates of previous room
                (prev_x, prev_y) = rooms[num_rooms-1].center()

                #draw a coin (random number that is either 0 or 1)
                if randint(0, 1) == 1:
                    #first move horizontally, then vertically
                    create_h_tunnel(prev_x, new_x, prev_y)
                    create_v_tunnel(prev_y, new_y, new_x)
                else:
                    #first move vertically, then horizontally
                    create_v_tunnel(prev_y, new_y, prev_x)
                    create_h_tunnel(prev_x, new_x, new_y)

            #finally, append the new room to the list
            rooms.append(new_room)
            num_rooms += 1

def player_death(player):
    #the game ended!
    global game_state
    print ('You died!')
    game_state = 'dead'

    #for added effect, transform the player into a corpse!
    player.char = '%'
    player.color = color_dark_red

def monster_death(monster):
    #transform it into a nasty corpse! it doesn't block, can't be
    #attacked and doesn't move
    print (monster.name.capitalize() + ' is dead!')
    monster.char = '%'
    monster.color = color_dark_red
    monster.blocks = False
    monster.fighter = None
    monster.ai = None
    monster.name = 'remains of ' + monster.name
    monster.send_to_back()

global visible_tiles
fighter_component = Fighter(hp=30, defense=2, power=5, death_function=player_death)
player = GameObject(0, 0, '@', 'player', [255, 255, 255], blocks=True, fighter=fighter_component)

objects = [player]

#generate map (at this point it's not drawn to the screen)
make_map()

def render_all():
    global color_dark_wall, color_light_wall
    global color_dark_ground, color_light_ground
    global fov_recompute, visible_tiles, player, map

    if fov_recompute:
        fov_recompute = False
        #print("fov_recompute")
        visible_tiles = tdl.map.quickFOV(player.x, player.y, is_visible_tile)
        #print(len(visible_tiles))
        #print(str(visible_tiles))
        #go through all tiles, and set their background color
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                visible = False
                coord = (x, y)
                #print(coord)
                if coord in visible_tiles:
                    #print("visible")
                    visible = True
                wall = map[x][y].block_sight
                if not visible:
                    if map[x][y].explored:
                        if wall:
                            # libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET )
                            con.drawChar(x, y, None, bgcolor = color_dark_wall)
                        else:
                            #libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET )
                            con.drawChar(x, y, None, bgcolor = color_dark_ground)
                else:
                    if wall:
                        con.drawChar(x, y, None, bgcolor = color_light_wall)

                    else:
                        con.drawChar(x, y, None, bgcolor = color_light_ground)
                        #print("yellow")
                    map[x][y].explored = True

    #draw all objects in the list, except the player. we want it to
    #always appear over all other objects! so it's drawn later.
    for object in objects:
        if object != player:
            object.draw()
    player.draw()
    console.blit(con, 0, 0, MAP_WIDTH, MAP_HEIGHT,0,0)
    #prepare to render the GUI panel
    #libtcod.console_set_default_background(panel, libtcod.black)
    #libtcod.console_clear(panel)
    panel.clear()

    #show the player's stats
    render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp,
        color_dark_red, color_yellow)

    #blit the contents of "panel" to the root console
    #libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)
    panel.move(0, 0)
    console.blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT)

def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
    #render a bar (HP, experience, etc). first calculate the width of the bar
    bar_width = int(float(value) / maximum * total_width)

    #render the background first
    #libtcod.console_set_default_background(panel, back_color)
    #panel.setColors(bg=back_color) # not used if there's no printStr call
    #libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)
    panel.drawRect(x, y, total_width, 1, None, None, back_color)

    #now render the bar on top
    #libtcod.console_set_default_background(panel, bar_color)
    #panel.setColors(bg=bar_color)
    if bar_width > 0:
        #libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)
        panel.drawRect(x, y, bar_width, 1, None, None, bar_color)

    #finally, some centered text with the values
    #libtcod.console_set_default_foreground(panel, libtcod.white)
    #panel.setColors(fg=[255,255,255])
    #libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER,
     #   name + ': ' + str(value) + '/' + str(maximum))
    #panel.printStr(name + ": " + str(value) + '/' + str(maximum))
    
    # prepare the text using old-style Python string formatting
    text = "%s: %i/%i" % (name, value, maximum)
    # then get a string spanning the entire bar with the text centered
    text = text.center(total_width)
    # render this text over the bar while preserving the background color
    panel.drawStr(x, y, text, [255,255,255], None)

def player_move_or_attack(dx, dy):
    global fov_recompute

    #the coordinates the player is moving to/attacking
    x = player.x + dx
    y = player.y + dy

    #try to find an attackable object there
    target = None
    for object in objects:
        if object.fighter and object.x == x and object.y == y:
            target = object
            break

    #attack if target found, move otherwise
    if target is not None:
        player.fighter.attack(target)
    else:
        player.move(dx, dy)
        fov_recompute = True

def handle_keys():
    global fov_recompute
    user_input = tdl.event.keyWait()
    if user_input.key == 'ESCAPE':
            return 'exit'
    if game_state == 'playing':
        if user_input.key == 'UP':
            player_move_or_attack(0, -1)
            fov_recompute = True
        elif user_input.key == 'DOWN':
            player_move_or_attack(0, 1)
            fov_recompute = True
        elif user_input.key == 'LEFT':
            player_move_or_attack(-1, 0)
            fov_recompute = True
        elif user_input.key == 'RIGHT':
            player_move_or_attack(1, 0)
            fov_recompute = True
        else:
            return 'didnt-take-turn'



#fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
for y in range(MAP_HEIGHT):
    for x in range(MAP_WIDTH):
        # libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)
        #tdl.map.quickFOV(x, y, map[x][y].block_sight )
        pass

fov_recompute = True
while not tdl.event.isWindowClosed():
    #render the screen
    render_all()

    tdl.flush()

    for obj in objects:
        obj.clear()

    player_action = handle_keys()

    if player_action == 'exit':
        break;

     #let monsters take their turn
    if game_state == 'playing' and player_action != 'didnt-take-turn':
        for object in objects:
            if object.ai:
                object.ai.take_turn()




