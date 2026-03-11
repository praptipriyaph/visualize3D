# visualize3D
A small project - it takes your 3D points as JSON and gives you an interactive browser view where you can drag to rotate and use the mouse wheel to zoom.

# use with inline ports
python3 visualize_points.py \ \n
  --points '[[0,0,0],[1,2,3],[-1,1,2]]' \ \n
  --output viewer.html

# from a json file
python3 project/visualize_points.py \
  --file sample_points.json \
  --output viewer.html

