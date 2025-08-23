from sqlalchemy.orm import Session
from sqlalchemy import text, and_
from models import LandPlot, PlotOrder
from schemas import PlotOrderCreate, PlotOrderResponse, OrderWithPlot
from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

class OrderService:
    
    def create_order(
        self, 
        db: Session, 
        plot_id: str, 
        order_data: PlotOrderCreate
    ) -> PlotOrderResponse:
        """Create a new plot order"""
        try:
            # Start transaction
            db.begin()
            
            # Create the order
            order = PlotOrder(
                plot_id=plot_id,
                customer_name=order_data.customer_name,
                customer_phone=order_data.customer_phone,
                customer_email=order_data.customer_email,
                customer_id_number=order_data.customer_id_number,
                intended_use=order_data.intended_use.value,
                notes=order_data.notes,
                status='pending'
            )
            
            db.add(order)
            db.flush()  # Get the order ID
            
            # Update plot status to pending
            plot = db.query(LandPlot).filter(LandPlot.id == plot_id).first()
            if plot:
                plot.status = 'pending'
                db.add(plot)
            
            db.commit()
            
            # Return the created order
            return PlotOrderResponse(
                id=str(order.id),
                plot_id=str(order.plot_id),
                customer_name=order.customer_name,
                customer_phone=order.customer_phone,
                customer_email=order.customer_email,
                customer_id_number=order.customer_id_number,
                intended_use=order.intended_use,
                notes=order.notes,
                status=order.status,
                created_at=order.created_at,
                updated_at=order.updated_at
            )
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating order for plot {plot_id}: {e}")
            raise
    
    def get_orders(
        self,
        db: Session,
        status: Optional[str] = None,
        plot_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[OrderWithPlot], int]:
        """Get orders with optional filtering"""
        try:
            # Build WHERE conditions
            conditions = []
            params = {"limit": limit, "offset": offset}
            
            if status:
                conditions.append("po.status = :status")
                params["status"] = status
            
            if plot_id:
                conditions.append("po.plot_id = :plot_id")
                params["plot_id"] = plot_id
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Get orders with plot information
            query = text(f"""
                SELECT 
                    po.id::text,
                    po.plot_id::text,
                    lp.plot_code,
                    po.customer_name,
                    po.customer_phone,
                    po.customer_email,
                    po.customer_id_number,
                    po.intended_use,
                    po.notes,
                    po.status,
                    po.created_at,
                    po.updated_at
                FROM plot_orders po
                JOIN land_plots lp ON po.plot_id = lp.id
                {where_clause}
                ORDER BY po.created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            result = db.execute(query, params)
            orders = result.fetchall()
            
            # Get total count
            count_query = text(f"""
                SELECT COUNT(*)
                FROM plot_orders po
                JOIN land_plots lp ON po.plot_id = lp.id
                {where_clause}
            """)
            
            total = db.execute(count_query, {k: v for k, v in params.items() 
                                          if k not in ['limit', 'offset']}).scalar()
            
            # Convert to response format
            order_list = []
            for order in orders:
                order_dict = {
                    "id": order.id,
                    "plot_id": order.plot_id,
                    "plot_code": order.plot_code,
                    "customer_name": order.customer_name,
                    "customer_phone": order.customer_phone,
                    "customer_email": order.customer_email,
                    "customer_id_number": order.customer_id_number,
                    "intended_use": order.intended_use,
                    "notes": order.notes,
                    "status": order.status,
                    "created_at": order.created_at.isoformat() + "Z",
                    "updated_at": order.updated_at.isoformat() + "Z"
                }
                order_list.append(order_dict)
            
            return order_list, total
            
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            raise
    
    def update_order_status(
        self,
        db: Session,
        order_id: str,
        new_status: str,
        notes: Optional[str] = None
    ) -> Optional[PlotOrder]:
        """Update order status and handle plot status changes"""
        try:
            db.begin()
            
            # Get the order
            order = db.query(PlotOrder).filter(PlotOrder.id == order_id).first()
            if not order:
                return None
            
            old_status = order.status
            order.status = new_status
            
            # Update plot status based on order status
            plot = db.query(LandPlot).filter(LandPlot.id == order.plot_id).first()
            if plot:
                if new_status == 'approved':
                    plot.status = 'taken'
                elif new_status == 'rejected':
                    # Check if there are other pending orders for this plot
                    other_pending = db.query(PlotOrder).filter(
                        and_(
                            PlotOrder.plot_id == order.plot_id,
                            PlotOrder.id != order.id,
                            PlotOrder.status == 'pending'
                        )
                    ).first()
                    
                    if not other_pending:
                        plot.status = 'available'
                
                db.add(plot)
            
            db.add(order)
            db.commit()
            
            logger.info(f"Order {order_id} status updated from {old_status} to {new_status}")
            return order
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating order {order_id} status: {e}")
            raise
    
    def get_order_by_id(self, db: Session, order_id: str) -> Optional[PlotOrder]:
        """Get order by ID"""
        try:
            return db.query(PlotOrder).filter(PlotOrder.id == order_id).first()
        except Exception as e:
            logger.error(f"Error fetching order {order_id}: {e}")
            raise