<?php

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class Net_Gain_Shows_List_Page {

	public static function render() {
		if ( ! current_user_can( Net_Gain_Admin_Menu::CAPABILITY ) ) {
			wp_die( 'You do not have permission to access this page.' );
		}

		$shows = get_posts(
			array(
				'post_type'      => Net_Gain_CPT_Show::POST_TYPE,
				'posts_per_page' => -1,
				'orderby'        => 'title',
				'order'          => 'ASC',
			)
		);

		$add_url = add_query_arg(
			array( 'page' => Net_Gain_Admin_Menu::EDIT_SLUG ),
			admin_url( 'admin.php' )
		);
		?>
		<div class="wrap">
			<h1 class="wp-heading-inline">Net Gain Studio — Shows</h1>
			<a href="<?php echo esc_url( $add_url ); ?>" class="page-title-action">Add New Show</a>
			<hr class="wp-header-end">

			<?php if ( empty( $shows ) ) : ?>
				<p>No shows yet. Click "Add New Show" to create the first one.</p>
			<?php else : ?>
				<table class="wp-list-table widefat fixed striped">
					<thead>
						<tr>
							<th>Name</th>
							<th>Vertical</th>
							<th>Status</th>
							<th>Primary Talent</th>
							<th></th>
						</tr>
					</thead>
					<tbody>
						<?php foreach ( $shows as $show ) : ?>
							<?php
							$vertical_id = (int) get_post_meta( $show->ID, 'ng_vertical_id', true );
							$vertical    = $vertical_id ? get_the_title( $vertical_id ) : '—';
							$status      = get_post_meta( $show->ID, 'ng_status', true );
							$primary_id  = Net_Gain_Talent_Assignments::get_effective_talent( $show->ID, current_time( 'Y-m-d' ) );
							$primary_user = $primary_id ? get_userdata( $primary_id ) : false;
							$primary     = $primary_user ? $primary_user->display_name : '—';
							$edit_url    = add_query_arg(
								array(
									'page'    => Net_Gain_Admin_Menu::EDIT_SLUG,
									'show_id' => $show->ID,
								),
								admin_url( 'admin.php' )
							);
							?>
							<tr>
								<td><a href="<?php echo esc_url( $edit_url ); ?>"><strong><?php echo esc_html( $show->post_title ); ?></strong></a></td>
								<td><?php echo esc_html( $vertical ); ?></td>
								<td><?php echo esc_html( ucfirst( $status ) ); ?></td>
								<td><?php echo esc_html( $primary ); ?></td>
								<td><a href="<?php echo esc_url( $edit_url ); ?>">Edit</a></td>
							</tr>
						<?php endforeach; ?>
					</tbody>
				</table>
			<?php endif; ?>
		</div>
		<?php
	}
}
