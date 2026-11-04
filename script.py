
# -*- coding: utf-8 -*-
__title__ = "PipeDirection Orbital"
__doc__ = "Selecciona una direccion, elimina el orbital y crea una tuberia con codo."

import math
import traceback

from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    XYZ,
    Line,
    Arc,
    Plane,
    SketchPlane,
    Transaction,
    View3D,
    Color,
    OverrideGraphicSettings,
    BuiltInParameter,
    ElementId
)

from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.UI.Selection import (
    ObjectType,
    ISelectionFilter
)
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms


uidoc = revit.uidoc
doc = revit.doc


# ------------------------------------------------------------
# CONFIGURACION
# ------------------------------------------------------------

ORBITAL_RADIUS_MM = 350.0
PIPE_LENGTH_MM = 1000.0
ELBOW_TAKEOFF_MM = 100.0

END_PICK_TOLERANCE_RATIO = 0.25

# Espacio central de las lineas radiales transversales.
TRANSVERSE_RADIAL_GAP_MM = 200.0

# Colores de los tres planos.
COLOR_TRANSVERSE = Color(0, 0, 255)
COLOR_LONG_A = Color(255, 0, 0)
COLOR_LONG_B = Color(0, 128, 0)
COLOR_SELECTED = Color(255, 230, 0)

ORBITAL_LINE_WEIGHT = 6
SELECTED_LINE_WEIGHT = 8

ORBITAL_SKETCH_PLANES = []


# ------------------------------------------------------------
# UTILIDADES GEOMETRICAS
# ------------------------------------------------------------

def normalize(vector):
    if vector is None or vector.GetLength() < 1e-9:
        raise Exception("No se puede normalizar un vector nulo.")

    return vector.Normalize()


def get_id_key(element_id):
    return element_id.IntegerValue


def mm_to_feet(value):
    return value / 304.8


def get_pipe_connectors(pipe):
    connectors = []

    for connector in pipe.ConnectorManager.Connectors:
        if connector.ConnectorType.ToString() == "End":
            connectors.append(connector)

    return connectors


def get_pipe_endpoints(pipe):
    location = pipe.Location

    if location is None or location.Curve is None:
        raise Exception(
            "La tuberia no tiene una curva de ubicacion valida."
        )

    curve = location.Curve

    return curve.GetEndPoint(0), curve.GetEndPoint(1)


def get_connector_near_point(connectors, point):
    if not connectors:
        raise Exception("No se encontraron conectores de extremo.")

    nearest = None
    nearest_distance = float("inf")

    for connector in connectors:
        distance = connector.Origin.DistanceTo(point)

        if distance < nearest_distance:
            nearest_distance = distance
            nearest = connector

    return nearest


def get_basis(axis):
    if abs(axis.DotProduct(XYZ.BasisZ)) < 0.90:
        reference = XYZ.BasisZ
    else:
        reference = XYZ.BasisX

    u = normalize(axis.CrossProduct(reference))
    v = normalize(axis.CrossProduct(u))

    return u, v


def point_on_plane(center, x_axis, y_axis, radius, angle):
    return (
        center
        + x_axis * (radius * math.cos(angle))
        + y_axis * (radius * math.sin(angle))
    )


# ------------------------------------------------------------
# SELECCION DE TUBERIA Y CONECTOR
# ------------------------------------------------------------

class PipeSelectionFilter(ISelectionFilter):

    def AllowElement(self, element):
        return isinstance(element, Pipe)

    def AllowReference(self, reference, position):
        return True


class SelectedPipePointFilter(ISelectionFilter):

    def __init__(self, pipe_id):
        self.pipe_id = pipe_id

    def AllowElement(self, element):
        return element.Id == self.pipe_id

    def AllowReference(self, reference, position):
        return reference.ElementId == self.pipe_id


def select_pipe():
    reference = uidoc.Selection.PickObject(
        ObjectType.Element,
        PipeSelectionFilter(),
        "Selecciona la tuberia existente."
    )

    pipe = doc.GetElement(reference.ElementId)

    if not isinstance(pipe, Pipe):
        raise Exception(
            "El elemento seleccionado no es una tuberia."
        )

    return pipe


def select_pipe_connector(pipe):
    connectors = get_pipe_connectors(pipe)

    if len(connectors) < 2:
        raise Exception(
            "No se encontraron los dos conectores de extremo."
        )

    point_reference = uidoc.Selection.PickObject(
        ObjectType.PointOnElement,
        SelectedPipePointFilter(pipe.Id),
        "Haz clic cerca del extremo donde deseas colocar el orbital."
    )

    picked_point = point_reference.GlobalPoint

    endpoint_0, endpoint_1 = get_pipe_endpoints(pipe)

    distance_0 = picked_point.DistanceTo(endpoint_0)
    distance_1 = picked_point.DistanceTo(endpoint_1)

    pipe_length = endpoint_0.DistanceTo(endpoint_1)
    tolerance = pipe_length * END_PICK_TOLERANCE_RATIO

    if distance_0 <= distance_1:
        selected_endpoint = endpoint_0
        other_endpoint = endpoint_1
        endpoint_distance = distance_0
    else:
        selected_endpoint = endpoint_1
        other_endpoint = endpoint_0
        endpoint_distance = distance_1

    if endpoint_distance > tolerance:
        raise Exception(
            "El punto seleccionado esta demasiado lejos de un extremo. "
            "Vuelve a ejecutar el comando y haz clic mas cerca."
        )

    connector = get_connector_near_point(
        connectors,
        selected_endpoint
    )

    outward_axis = normalize(
        selected_endpoint - other_endpoint
    )

    return connector, outward_axis


# ------------------------------------------------------------
# CREACION DE CURVAS DEL ORBITAL
# ------------------------------------------------------------

def create_sketch_plane(origin, x_axis, y_axis):
    plane = Plane.CreateByOriginAndBasis(
        origin,
        x_axis,
        y_axis
    )

    sketch_plane = SketchPlane.Create(doc, plane)
    ORBITAL_SKETCH_PLANES.append(sketch_plane.Id)

    return sketch_plane


def create_model_line(start_point, end_point, sketch_plane):
    line = Line.CreateBound(
        start_point,
        end_point
    )

    return doc.Create.NewModelCurve(
        line,
        sketch_plane
    )


def create_arc_piece(
    center,
    radius,
    start_angle,
    end_angle,
    x_axis,
    y_axis,
    sketch_plane
):
    arc = Arc.Create(
        center,
        radius,
        start_angle,
        end_angle,
        x_axis,
        y_axis
    )

    return doc.Create.NewModelCurve(
        arc,
        sketch_plane
    )


def create_full_orbit(center, radius, x_axis, y_axis):
    sketch_plane = create_sketch_plane(
        center,
        x_axis,
        y_axis
    )

    elements = []

    elements.append(
        create_arc_piece(
            center,
            radius,
            0.0,
            math.pi,
            x_axis,
            y_axis,
            sketch_plane
        )
    )

    elements.append(
        create_arc_piece(
            center,
            radius,
            math.pi,
            2.0 * math.pi,
            x_axis,
            y_axis,
            sketch_plane
        )
    )

    return elements


def create_semicircle_outward(
    center,
    radius,
    x_axis,
    outward_axis
):
    sketch_plane = create_sketch_plane(
        center,
        x_axis,
        outward_axis
    )

    element = create_arc_piece(
        center,
        radius,
        0.0,
        math.pi,
        x_axis,
        outward_axis,
        sketch_plane
    )

    return [element]


# ------------------------------------------------------------
# LINEAS RECTAS SELECCIONABLES
# ------------------------------------------------------------

def create_radial_lines(
    center,
    radius,
    x_axis,
    y_axis,
    angles_degrees,
    labels,
    direction_map,
    inner_radius=0.0
):
    """
    Crea lineas radiales seleccionables.

    inner_radius = 0:
        La linea comienza en el centro.

    inner_radius > 0:
        La linea comienza separada del centro y termina
        en la circunferencia exterior.
    """

    sketch_plane = create_sketch_plane(
        center,
        x_axis,
        y_axis
    )

    elements = []

    for index, angle_degrees in enumerate(angles_degrees):
        angle = math.radians(angle_degrees)

        # Punto inicial de la linea.
        start_point = point_on_plane(
            center,
            x_axis,
            y_axis,
            inner_radius,
            angle
        )

        # Punto final sobre la circunferencia exterior.
        end_point = point_on_plane(
            center,
            x_axis,
            y_axis,
            radius,
            angle
        )

        element = create_model_line(
            start_point,
            end_point,
            sketch_plane
        )

        # La direccion conserva el sentido radial desde el centro.
        # El espacio interior no altera el vector seleccionado.
        radial_vector = (
            x_axis * math.cos(angle)
            + y_axis * math.sin(angle)
        )

        vector = normalize(radial_vector)
        element_key = get_id_key(element.Id)

        direction_map[element_key] = (
            labels[index],
            vector
        )

        elements.append(element)

    return elements


# ------------------------------------------------------------
# COLORES Y GROSOR DE LINEAS
# ------------------------------------------------------------

def apply_view_color(view, elements, color):
    settings = OverrideGraphicSettings()
    settings.SetProjectionLineColor(color)
    settings.SetProjectionLineWeight(ORBITAL_LINE_WEIGHT)

    for element in elements:
        view.SetElementOverrides(
            element.Id,
            settings
        )


# ------------------------------------------------------------
# CREACION DEL ORBITAL 3D
# ------------------------------------------------------------

def create_orbital(center, outward_axis):
    radius = mm_to_feet(ORBITAL_RADIUS_MM)
    transverse_gap = mm_to_feet(TRANSVERSE_RADIAL_GAP_MM)

    u, v = get_basis(outward_axis)

    direction_map = {}

    # --------------------------------------------------------
    # PLANO TRANSVERSAL
    # Circunferencia completa y ocho lineas cada 45 grados.
    # Las lineas dejan un espacio alrededor del centro.
    # --------------------------------------------------------

    transverse_elements = []

    # Mantener la circunferencia transversal completa.
    transverse_elements.extend(
        create_full_orbit(
            center,
            radius,
            u,
            v
        )
    )

    transverse_angles = [
        0,
        45,
        90,
        135,
        180,
        225,
        270,
        315
    ]

    transverse_labels = [
        "Transversal - 0 grados",
        "Transversal - 45 grados",
        "Transversal - 90 grados",
        "Transversal - 135 grados",
        "Transversal - 180 grados",
        "Transversal - 225 grados",
        "Transversal - 270 grados",
        "Transversal - 315 grados"
    ]

    transverse_elements.extend(
        create_radial_lines(
            center,
            radius,
            u,
            v,
            transverse_angles,
            transverse_labels,
            direction_map,
            inner_radius=transverse_gap
        )
    )

    # --------------------------------------------------------
    # PLANO LONGITUDINAL A
    # Sin cambios: las lineas parten del centro.
    # --------------------------------------------------------

    longitudinal_a_elements = []

    longitudinal_a_elements.extend(
        create_semicircle_outward(
            center,
            radius,
            u,
            outward_axis
        )
    )

    longitudinal_a_elements.extend(
        create_radial_lines(
            center,
            radius,
            u,
            outward_axis,
            [0, 45, 90, 135, 180],
            [
                "Longitudinal A - 0 grados",
                "Longitudinal A - 45 grados",
                "Longitudinal A - 90 grados",
                "Longitudinal A - 135 grados",
                "Longitudinal A - 180 grados"
            ],
            direction_map
        )
    )

    # --------------------------------------------------------
    # PLANO LONGITUDINAL B
    # Sin cambios: las lineas parten del centro.
    # --------------------------------------------------------

    longitudinal_b_elements = []

    longitudinal_b_elements.extend(
        create_semicircle_outward(
            center,
            radius,
            v,
            outward_axis
        )
    )

    longitudinal_b_elements.extend(
        create_radial_lines(
            center,
            radius,
            v,
            outward_axis,
            [0, 45, 90, 135, 180],
            [
                "Longitudinal B - 90 grados",
                "Longitudinal B - 135 grados",
                "Longitudinal B - 180 grados",
                "Longitudinal B - 225 grados",
                "Longitudinal B - 270 grados"
            ],
            direction_map
        )
    )

    # --------------------------------------------------------
    # APLICAR COLORES
    # --------------------------------------------------------

    view = doc.ActiveView

    apply_view_color(
        view,
        transverse_elements,
        COLOR_TRANSVERSE
    )

    apply_view_color(
        view,
        longitudinal_a_elements,
        COLOR_LONG_A
    )

    apply_view_color(
        view,
        longitudinal_b_elements,
        COLOR_LONG_B
    )

    all_elements = (
        transverse_elements
        + longitudinal_a_elements
        + longitudinal_b_elements
    )

    return all_elements, direction_map


# ------------------------------------------------------------
# FILTRO DE SELECCION DEL ORBITAL
# ------------------------------------------------------------

class OrbitalLineSelectionFilter(ISelectionFilter):

    def __init__(self, direction_map):
        self.allowed_ids = set(direction_map.keys())

    def AllowElement(self, element):
        try:
            return get_id_key(element.Id) in self.allowed_ids
        except:
            return False

    def AllowReference(self, reference, position):
        try:
            return get_id_key(reference.ElementId) in self.allowed_ids
        except:
            return False


# ------------------------------------------------------------
# SELECCION DIRECTA DE UNA LINEA
# ------------------------------------------------------------

def select_orbital_direction(direction_map):
    selection_filter = OrbitalLineSelectionFilter(
        direction_map
    )

    reference = uidoc.Selection.PickObject(
        ObjectType.Element,
        selection_filter,
        "Selecciona una LINEA RECTA del orbital. "
        "Pulsa ESC para cancelar."
    )

    key = get_id_key(reference.ElementId)

    if key not in direction_map:
        raise Exception(
            "La linea seleccionada no tiene una direccion registrada."
        )

    label, vector = direction_map[key]

    return label, vector


# ------------------------------------------------------------
# ELIMINAR ORBITAL Y PLANOS DE TRABAJO
# ------------------------------------------------------------

def delete_orbital(elements):
    ids_to_delete = List[ElementId]()

    for element in elements:
        ids_to_delete.Add(element.Id)

    for sketch_plane_id in ORBITAL_SKETCH_PLANES:
        ids_to_delete.Add(sketch_plane_id)

    doc.Delete(ids_to_delete)

    ORBITAL_SKETCH_PLANES[:] = []


# ------------------------------------------------------------
# CREAR TUBERIA Y COLOCAR CODO
# ------------------------------------------------------------

def create_pipe_with_elbow(
    source_pipe,
    source_connector,
    direction
):
    if source_connector.IsConnected:
        raise Exception(
            "El conector seleccionado ya esta conectado.\n\n"
            "Para esta prueba, selecciona un extremo libre de la "
            "tuberia existente. No se modificara una conexion previa."
        )

    direction = normalize(direction)

    takeoff = mm_to_feet(ELBOW_TAKEOFF_MM)
    pipe_length = mm_to_feet(PIPE_LENGTH_MM)

    source_point = source_connector.Origin

    new_start = source_point + direction * takeoff
    new_end = new_start + direction * pipe_length

    system_parameter = source_pipe.get_Parameter(
        BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM
    )

    if system_parameter is None:
        raise Exception(
            "No se pudo obtener el tipo de sistema de la tuberia."
        )

    system_type_id = system_parameter.AsElementId()

    if system_type_id == ElementId.InvalidElementId:
        raise Exception(
            "La tuberia original no tiene un tipo de sistema valido."
        )

    level = source_pipe.ReferenceLevel

    if level is None:
        raise Exception(
            "No se pudo obtener el nivel de referencia de la tuberia."
        )

    pipe_type_id = source_pipe.GetTypeId()

    diameter_parameter = source_pipe.get_Parameter(
        BuiltInParameter.RBS_PIPE_DIAMETER_PARAM
    )

    if diameter_parameter is None:
        raise Exception(
            "No se pudo obtener el diametro de la tuberia original."
        )

    diameter = diameter_parameter.AsDouble()

    new_pipe = Pipe.Create(
        doc,
        system_type_id,
        pipe_type_id,
        level.Id,
        new_start,
        new_end
    )

    new_diameter_parameter = new_pipe.get_Parameter(
        BuiltInParameter.RBS_PIPE_DIAMETER_PARAM
    )

    if (
        new_diameter_parameter is not None
        and not new_diameter_parameter.IsReadOnly
    ):
        new_diameter_parameter.Set(diameter)

    doc.Regenerate()

    new_connectors = get_pipe_connectors(new_pipe)

    new_start_connector = get_connector_near_point(
        new_connectors,
        new_start
    )

    elbow = doc.Create.NewElbowFitting(
        source_connector,
        new_start_connector
    )

    doc.Regenerate()

    return new_pipe, elbow, diameter


# ------------------------------------------------------------
# PROCESO PRINCIPAL
# ------------------------------------------------------------

def main():

    if not isinstance(doc.ActiveView, View3D):
        forms.alert(
            "Abre una vista 3D de Revit y vuelve a ejecutar "
            "PipeDirection Orbital.",
            title="PipeDirection"
        )
        return

    try:
        # 1. Seleccionar la tuberia existente.
        source_pipe = select_pipe()

        # 2. Elegir el extremo.
        source_connector, outward_axis = select_pipe_connector(
            source_pipe
        )

        center = source_connector.Origin

        # 3. Crear el orbital temporal.
        ORBITAL_SKETCH_PLANES[:] = []

        transaction = Transaction(
            doc,
            "PipeDirection - Crear orbital temporal"
        )

        transaction.Start()

        try:
            orbital_elements, direction_map = create_orbital(
                center,
                outward_axis
            )

            transaction.Commit()

        except:
            transaction.RollBack()
            ORBITAL_SKETCH_PLANES[:] = []
            raise

        # 4. Seleccionar directamente una linea radial.
        try:
            label, direction = select_orbital_direction(
                direction_map
            )

        except:
            cleanup_transaction = Transaction(
                doc,
                "PipeDirection - Eliminar orbital cancelado"
            )

            cleanup_transaction.Start()

            try:
                delete_orbital(orbital_elements)
                cleanup_transaction.Commit()

            except:
                cleanup_transaction.RollBack()
                raise

            raise

        # 5. Eliminar el orbital despues de seleccionar.
        transaction = Transaction(
            doc,
            "PipeDirection - Eliminar orbital temporal"
        )

        transaction.Start()

        try:
            delete_orbital(orbital_elements)
            transaction.Commit()

        except:
            transaction.RollBack()
            raise

        # 6. Crear la tuberia y el codo.
        transaction = Transaction(
            doc,
            "PipeDirection - Crear tuberia y codo"
        )

        transaction.Start()

        try:
            new_pipe, elbow, diameter = create_pipe_with_elbow(
                source_pipe,
                source_connector,
                direction
            )

            transaction.Commit()

        except:
            transaction.RollBack()
            raise

    except OperationCanceledException:
        pass

    except Exception as ex:
        forms.alert(
            "No se pudo completar la prueba.\n\n"
            + str(ex)
            + "\n\n"
            + traceback.format_exc(),
            title="PipeDirection - Error"
        )


if __name__ == "__main__":
    main()
